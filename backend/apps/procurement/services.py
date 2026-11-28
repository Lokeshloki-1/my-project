"""
Workflow for material requirements, RFQs and supplier POs.
Status changes go through functions here: they lock the row, check the transition and log it.
"""

import logging
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.services import Conflict, is_manager
from apps.development.models import TechPack
from apps.merchandising.models import OrderConfirmation

from .models import (
    ActivityLog,
    MaterialRequirement,
    PurchaseOrder,
    PurchaseOrderLine,
    RequirementLine,
    RFQ,
    SupplierQuote,
    SupplierQuoteLine,
    ceil2,
    dec,
)

logger = logging.getLogger(__name__)


def log(doc_type, doc, action, user, note=""):
    ActivityLog.objects.create(doc_type=doc_type, doc_id=doc.pk, action=action, user=user, note=note)
    logger.info("%s %s %s user=%s", doc_type, doc.pk, action, getattr(user, "pk", None))


def history(doc_type, doc_id):
    return ActivityLog.objects.filter(doc_type=doc_type, doc_id=doc_id).select_related("user")


def _lock(model, obj):
    return model.objects.select_for_update().get(pk=obj.pk)


def ensure_draft(doc, label):
    if doc.status != "draft":
        raise Conflict(f"This {label} is {doc.get_status_display().lower()} and can no longer be edited.")


def require_manager(user, what):
    if not is_manager(user):
        raise PermissionDenied(f"Only managers and admins can {what}.")


# ---------------------------------------------------------------- requirements

def ordered_qty_annotation():
    """Σ quantity on PO lines that are not cancelled, for each requirement line."""
    return Coalesce(
        Sum("po_lines__quantity", filter=~Q(po_lines__order__status=PurchaseOrder.Status.CANCELLED)),
        Value(Decimal("0")), output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def calculate_lines(order, wastage_pct):
    """(lines, warnings) for an order: order qty × BOM consumption, merged across styles."""
    merged, warnings = OrderedDict(), []
    factor = 1 + dec(wastage_pct) / 100
    for line in order.lines.all():
        tp = (TechPack.objects.filter(buyer=order.buyer, style_no=line.style_no, status=TechPack.Status.RELEASED)
              .prefetch_related("bom").order_by("-revision").first())
        if tp is None:
            warnings.append(f"{line.style_no}: no released tech pack, so its materials are not included.")
            continue
        if not tp.production_approved:
            warnings.append(f"{line.style_no}: PP sample not approved yet — check the BOM before buying.")
        for item in tp.bom.all():
            if item.consumption is None:
                warnings.append(f"{line.style_no}: “{item.description}” has no consumption in the tech pack; add it by hand.")
                continue
            key = (item.category, item.description.strip().lower(), item.colour.strip().lower(), item.unit.strip().lower())
            row = merged.setdefault(key, {
                "category": item.category, "description": item.description, "colour": item.colour,
                "unit": item.unit or "pc", "supplier_hint": item.supplier, "styles": [], "net": Decimal("0"),
            })
            row["net"] += line.quantity * item.consumption
            if line.style_no not in row["styles"]:
                row["styles"].append(line.style_no)
    lines = [
        RequirementLine(
            category=r["category"], description=r["description"], colour=r["colour"], unit=r["unit"],
            supplier_hint=r["supplier_hint"], styles=", ".join(r["styles"]), net_qty=ceil2(r["net"]),
            required_qty=ceil2(r["net"] * factor), position=i,
        )
        for i, r in enumerate(merged.values())
    ]
    return lines, warnings


@transaction.atomic
def generate_requirement(order, user, wastage_pct=Decimal("5")):
    """Material requirement for a confirmed order. Calling it again returns the existing one."""
    order = OrderConfirmation.objects.select_for_update().get(pk=order.pk)
    existing = MaterialRequirement.objects.filter(order=order).first()
    if existing:
        return existing, False
    if order.status != OrderConfirmation.Status.CONFIRMED:
        raise Conflict("Material requirements are made from confirmed orders.")
    lines, warnings = calculate_lines(order, wastage_pct)
    mr = MaterialRequirement.objects.create(
        company=order.company, order=order, buyer=order.buyer, wastage_pct=wastage_pct, warnings=warnings,
        title=f"Materials for {order.oc_no} · {order.buyer.legal_name} PO {order.buyer_po_no}",
        needed_by=(order.ship_date - timedelta(days=45)) if order.ship_date else None, created_by=user,
    )
    for line in lines:
        line.requirement = mr
    RequirementLine.objects.bulk_create(lines)
    log("requirement", mr, "created", user, f"{len(lines)} materials from {order.oc_no}, wastage {wastage_pct}%")
    return mr, True


@transaction.atomic
def recalculate_requirement(mr, user):
    """Rebuild the lines from the order and tech packs (draft only, e.g. after the BOM changed)."""
    mr = _lock(MaterialRequirement, mr)
    ensure_draft(mr, "requirement")
    if not mr.order_id:
        raise Conflict("This requirement was not made from an order.")
    if RequirementLine.objects.filter(requirement=mr).filter(Q(po_lines__isnull=False) | Q(rfq_lines__isnull=False)).exists():
        raise Conflict("Some lines are already on an RFQ or PO; edit the lines by hand instead.")
    lines, warnings = calculate_lines(mr.order, mr.wastage_pct)
    mr.lines.all().delete()
    for line in lines:
        line.requirement = mr
    RequirementLine.objects.bulk_create(lines)
    mr.warnings = warnings
    mr.save(update_fields=["warnings", "updated_at"])
    log("requirement", mr, "recalculated", user, f"{len(lines)} materials")
    return mr


def requirement_actions(mr, user):
    actions = []
    if mr.status == MaterialRequirement.Status.DRAFT:
        actions += ["edit"] + (["recalculate"] if mr.order_id else []) + (["approve"] if is_manager(user) else [])
    else:
        actions += ["create_rfq", "create_po"]
        if is_manager(user):
            actions.append("reopen")
    return actions


@transaction.atomic
def approve_requirement(mr, user):
    require_manager(user, "approve material requirements")
    mr = _lock(MaterialRequirement, mr)
    if mr.status == MaterialRequirement.Status.APPROVED:
        return mr
    if not mr.lines.filter(required_qty__gt=0).exists():
        raise ValidationError({"lines": "There are no materials with a quantity to buy."})
    mr.status = MaterialRequirement.Status.APPROVED
    mr.approved_by, mr.approved_at = user, timezone.now()
    mr.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log("requirement", mr, "approved", user)
    return mr


@transaction.atomic
def reopen_requirement(mr, user):
    require_manager(user, "reopen material requirements")
    mr = _lock(MaterialRequirement, mr)
    if mr.status != MaterialRequirement.Status.APPROVED:
        raise Conflict("Only approved requirements can be reopened.")
    mr.status = MaterialRequirement.Status.DRAFT
    mr.approved_by = mr.approved_at = None
    mr.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log("requirement", mr, "reopened", user)
    return mr


def check_requirement_lines(lines, company):
    """Lines taken from a requirement must be from an approved requirement of the same company."""
    for line in lines:
        rl = line.get("requirement_line")
        if rl is None:
            continue
        if rl.requirement.company_id != company.id:
            raise ValidationError({"lines": f"“{rl.description}” belongs to another company."})
        if rl.requirement.status != MaterialRequirement.Status.APPROVED:
            raise ValidationError({"lines": f"Requirement {rl.requirement.mr_no} is not approved yet."})


# ---------------------------------------------------------------- RFQs

def rfq_actions(rfq, user):
    s = RFQ.Status
    return {
        s.DRAFT: ["edit", "send", "cancel"],
        s.SENT: ["record_quote", "award", "cancel"],
        s.AWARDED: ["view_po"],
        s.CANCELLED: [],
    }[rfq.status]


@transaction.atomic
def send_rfq(rfq, user):
    rfq = _lock(RFQ, rfq)
    ensure_draft(rfq, "RFQ")
    missing = {}
    if not rfq.lines.exists():
        missing["lines"] = "Add the materials to quote for."
    if not rfq.suppliers.exists():
        missing["suppliers"] = "Choose at least one supplier."
    if missing:
        raise ValidationError(missing)
    rfq.status, rfq.sent_at = RFQ.Status.SENT, timezone.now()
    rfq.save(update_fields=["status", "sent_at", "updated_at"])
    names = ", ".join(s.name for s in rfq.suppliers.all())
    log("rfq", rfq, "sent", user, f"To {names}")
    return rfq


@transaction.atomic
def record_quote(rfq, user, supplier, data, lines):
    """Create or replace a supplier's quote. lines = [{"rfq_line": RFQLine, "unit_price": .., "lead_time_days": ..}]"""
    rfq = _lock(RFQ, rfq)
    if rfq.status != RFQ.Status.SENT:
        raise Conflict("Quotes can only be recorded while the RFQ is out with suppliers.")
    if not rfq.suppliers.filter(pk=supplier.pk).exists():
        raise ValidationError({"supplier": f"{supplier.name} was not invited to this RFQ."})
    rfq_line_ids = set(rfq.lines.values_list("id", flat=True))
    for line in lines:
        if line["rfq_line"].id not in rfq_line_ids:
            raise ValidationError({"lines": "A price is for a line of another RFQ."})
    quote, _ = SupplierQuote.objects.update_or_create(rfq=rfq, supplier=supplier, defaults=data)
    quote.lines.all().delete()
    for line in lines:
        SupplierQuoteLine.objects.create(quote=quote, **line)
    quote.total = sum((ql.amount for ql in quote.lines.all()), Decimal("0"))
    quote.complete = quote.lines.count() == len(rfq_line_ids)
    quote.save(update_fields=["total", "complete"])
    log("rfq", rfq, "quote_recorded", user, f"{supplier.name}: {quote.currency} {quote.total}" + ("" if quote.complete else " (partial)"))
    return quote


def comparison(rfq):
    """Per line: each supplier's price and the lowest one; per supplier: totals."""
    quotes = list(rfq.quotes.select_related("supplier").prefetch_related("lines"))
    prices = {(ql.rfq_line_id, q.supplier_id): ql for q in quotes for ql in q.lines.all()}
    lines = []
    for line in rfq.lines.all():
        offers = [
            {"supplier": q.supplier_id, "unit_price": prices[(line.id, q.supplier_id)].unit_price,
             "amount": prices[(line.id, q.supplier_id)].amount, "lead_time_days": prices[(line.id, q.supplier_id)].lead_time_days}
            for q in quotes if (line.id, q.supplier_id) in prices
        ]
        best = min((o["unit_price"] for o in offers), default=None)
        for o in offers:
            o["best"] = o["unit_price"] == best
        lines.append({"rfq_line": line.id, "offers": offers})
    complete = [q for q in quotes if q.complete]
    lowest = min(complete, key=lambda q: q.total) if complete else None
    return {
        "lines": lines,
        "suppliers": [
            {"supplier": q.supplier_id, "supplier_name": q.supplier.name, "currency": q.currency, "total": q.total,
             "complete": q.complete, "valid_until": q.valid_until, "payment_terms": q.payment_terms, "notes": q.notes,
             "lowest": lowest is not None and q.id == lowest.id}
            for q in quotes
        ],
    }


@transaction.atomic
def award_rfq(rfq, user, supplier):
    """Award the RFQ to a supplier with a complete quote and create a draft PO from it."""
    rfq = _lock(RFQ, rfq)
    if rfq.status == RFQ.Status.AWARDED:
        return rfq.purchase_orders.first()
    if rfq.status != RFQ.Status.SENT:
        raise Conflict("Only an RFQ that is out with suppliers can be awarded.")
    quote = rfq.quotes.filter(supplier=supplier).prefetch_related("lines__rfq_line").first()
    if quote is None:
        raise ValidationError({"supplier": f"{supplier.name} has not quoted."})
    if not quote.complete:
        raise ValidationError({"supplier": f"{supplier.name} did not price every line."})
    po = PurchaseOrder.objects.create(
        company=rfq.company, supplier=supplier, requirement=rfq.requirement, rfq=rfq, order_date=timezone.localdate(),
        delivery_date=rfq.required_by, currency=quote.currency, payment_terms=quote.payment_terms or supplier.payment_terms,
        delivery_address=rfq.company.address, created_by=user,
    )
    for i, ql in enumerate(sorted(quote.lines.all(), key=lambda q: q.rfq_line.position)):
        rl = ql.rfq_line
        PurchaseOrderLine.objects.create(
            order=po, requirement_line=rl.requirement_line, category=rl.category, description=rl.description,
            colour=rl.colour, unit=rl.unit, quantity=rl.quantity, unit_price=ql.unit_price, position=i,
        )
    po.recalculate()
    rfq.status, rfq.awarded_supplier = RFQ.Status.AWARDED, supplier
    rfq.save(update_fields=["status", "awarded_supplier", "updated_at"])
    log("rfq", rfq, "awarded", user, f"{supplier.name}, {quote.currency} {quote.total} → {po.po_no}")
    log("po", po, "created", user, f"From {rfq.rfq_no}")
    return po


@transaction.atomic
def cancel_rfq(rfq, user, reason=""):
    rfq = _lock(RFQ, rfq)
    if rfq.status not in (RFQ.Status.DRAFT, RFQ.Status.SENT):
        raise Conflict("Only draft or sent RFQs can be cancelled.")
    rfq.status = RFQ.Status.CANCELLED
    rfq.save(update_fields=["status", "updated_at"])
    log("rfq", rfq, "cancelled", user, reason)
    return rfq


# ---------------------------------------------------------------- purchase orders

def po_actions(po, user):
    s = PurchaseOrder.Status
    actions = []
    if po.status == s.DRAFT:
        actions += ["edit", "delete", "cancel"] + (["approve"] if is_manager(user) else [])
    elif po.status == s.APPROVED:
        actions += ["send"] + (["cancel"] if is_manager(user) else [])
    elif po.status == s.SENT and is_manager(user):
        actions.append("cancel")
    return actions


def over_ordered(po):
    """Requirement lines this PO would take over their required quantity: [(line, ordered incl. this PO)]."""
    ids = [line.requirement_line_id for line in po.lines.all() if line.requirement_line_id]
    rows = RequirementLine.objects.filter(id__in=ids).annotate(ordered=ordered_qty_annotation())
    return [r for r in rows if r.ordered > r.required_qty]


@transaction.atomic
def approve_po(po, user):
    require_manager(user, "approve purchase orders")
    po = _lock(PurchaseOrder, po)
    if po.status == PurchaseOrder.Status.APPROVED:
        return po
    ensure_draft(po, "purchase order")
    if not po.lines.exists():
        raise ValidationError({"lines": "The PO has no lines."})
    if not po.supplier.is_active:
        raise ValidationError({"supplier": f"{po.supplier.name} is inactive."})
    po.status, po.approved_by, po.approved_at = PurchaseOrder.Status.APPROVED, user, timezone.now()
    po.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    over = over_ordered(po)
    note = f"{po.currency} {po.total}"
    if over:
        note += ". Over the requirement: " + ", ".join(f"{r.description} ({r.ordered}/{r.required_qty} {r.unit})" for r in over)
    log("po", po, "approved", user, note)
    return po


@transaction.atomic
def send_po(po, user):
    po = _lock(PurchaseOrder, po)
    if po.status == PurchaseOrder.Status.SENT:
        return po
    if po.status != PurchaseOrder.Status.APPROVED:
        raise Conflict("Only approved purchase orders can be sent to the supplier.")
    po.status, po.sent_at = PurchaseOrder.Status.SENT, timezone.now()
    po.save(update_fields=["status", "sent_at", "updated_at"])
    log("po", po, "sent", user, f"To {po.supplier.name}" + (f" ({po.supplier.email})" if po.supplier.email else ""))
    return po


@transaction.atomic
def cancel_po(po, user, reason):
    if not reason:
        raise ValidationError({"reason": "Give a reason for cancelling."})
    po = _lock(PurchaseOrder, po)
    if po.status == PurchaseOrder.Status.CANCELLED:
        raise Conflict("This PO is already cancelled.")
    if po.status != PurchaseOrder.Status.DRAFT and not is_manager(user):
        raise PermissionDenied("Only managers and admins can cancel an approved purchase order.")
    po.status, po.cancel_reason = PurchaseOrder.Status.CANCELLED, reason
    po.save(update_fields=["status", "cancel_reason", "updated_at"])
    log("po", po, "cancelled", user, reason)
    return po
