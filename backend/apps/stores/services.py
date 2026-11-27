"""
Raw material stock. Every on-hand change is a MaterialMovement written together with the
MaterialStock balance, inside a transaction, with the stock row locked — so two people
can't take the same material at once.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.services import Conflict, is_manager
from apps.merchandising.models import OrderConfirmation
from apps.procurement.models import PurchaseOrder

from .models import ActivityLog, GoodsReceipt, GoodsReceiptLine, Material, MaterialAllocation, MaterialMovement, MaterialStock

logger = logging.getLogger(__name__)
ZERO = Decimal("0")
TWO = Decimal("0.01")
OVER_RECEIPT_TOLERANCE = Decimal("0.10")  # mills often ship a little more than ordered


def q2(v):
    return Decimal(v).quantize(TWO, ROUND_HALF_UP)


def log(doc_type, doc, action, user, note=""):
    ActivityLog.objects.create(doc_type=doc_type, doc_id=doc.pk, action=action, user=user, note=note)
    logger.info("%s %s %s user=%s", doc_type, doc.pk, action, getattr(user, "pk", None))


def history(doc_type, doc_id):
    return ActivityLog.objects.filter(doc_type=doc_type, doc_id=doc_id).select_related("user")


# ---------------------------------------------------------------- materials & stock

def material_for(company, category, description, colour, unit):
    """The stock item for this material (case-insensitive match), created if new."""
    description, colour, unit = description.strip(), (colour or "").strip(), (unit or "pc").strip()
    found = Material.objects.filter(
        company=company, category=category, description__iexact=description, colour__iexact=colour, unit__iexact=unit
    ).first()
    return found or Material.objects.create(company=company, category=category, description=description, colour=colour, unit=unit)


def match_material(company, category, description, colour, unit):
    return Material.objects.filter(
        company=company, category=category, description__iexact=description.strip(),
        colour__iexact=(colour or "").strip(), unit__iexact=(unit or "").strip(),
    ).first()


def _locked_stock(material, warehouse):
    MaterialStock.objects.get_or_create(material=material, warehouse=warehouse)
    return MaterialStock.objects.select_for_update().get(material=material, warehouse=warehouse)


def _check_warehouse(material, warehouse):
    if warehouse.company_id != material.company_id:
        raise ValidationError({"warehouse": "That warehouse belongs to another company."})


def _move(stock, quantity, movement_type, user, unit_cost=None, **refs):
    """Change on hand by `quantity` (locked stock row) and write the ledger row."""
    new_on_hand = stock.on_hand + quantity
    if new_on_hand < 0:
        raise ValidationError({"quantity": f"Only {stock.on_hand} {stock.material.unit} of {stock.material} in {stock.warehouse.name}."})
    if new_on_hand < stock.allocated:
        raise ValidationError({"quantity": f"{stock.allocated} {stock.material.unit} is allocated to orders; release it first."})
    if quantity > 0:
        cost = unit_cost if unit_cost is not None else stock.average_cost
        stock.value = q2(stock.value + quantity * cost)
    else:
        cost = stock.average_cost
        stock.value = q2(max(stock.value + quantity * cost, ZERO)) if new_on_hand else ZERO
    stock.on_hand = new_on_hand
    stock.save(update_fields=["on_hand", "value", "allocated", "updated_at"])
    return MaterialMovement.objects.create(
        material=stock.material, warehouse=stock.warehouse, movement_type=movement_type, quantity=quantity,
        balance_after=new_on_hand, unit_cost=cost, created_by=user, **refs,
    )


@transaction.atomic
def adjust_stock(material, warehouse, new_quantity, reason, user):
    """Set on hand to a counted quantity (manager only)."""
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can adjust stock.")
    if not reason:
        raise ValidationError({"reason": "Give a reason, e.g. stock count on 30 Nov."})
    _check_warehouse(material, warehouse)
    stock = _locked_stock(material, warehouse)
    delta = Decimal(new_quantity) - stock.on_hand
    if delta == 0:
        raise ValidationError({"new_quantity": "That is already the quantity on hand."})
    return _move(stock, delta, MaterialMovement.Type.ADJUSTMENT, user, note=reason, reference="Stock count")


# ---------------------------------------------------------------- goods receipt

def received_so_far(po_line, exclude_receipt=None):
    """Quantity on GRNs that were submitted (not drafts) for this PO line."""
    qs = po_line.grn_lines.exclude(receipt__status=GoodsReceipt.Status.DRAFT)
    if exclude_receipt is not None:
        qs = qs.exclude(receipt=exclude_receipt)
    return qs.aggregate(t=Sum("received_qty"))["t"] or ZERO


def accepted_so_far(po_line):
    return po_line.grn_lines.filter(receipt__status=GoodsReceipt.Status.INSPECTED).aggregate(t=Sum("accepted_qty"))["t"] or ZERO


def receivable_lines(po):
    rows = []
    for line in po.lines.all():
        received = received_so_far(line)
        rows.append({
            "po_line": line.id, "category": line.category, "description": line.description, "colour": line.colour,
            "unit": line.unit, "ordered_qty": line.quantity, "received_qty": received, "accepted_qty": accepted_so_far(line),
            "open_qty": max(line.quantity - received, ZERO), "unit_price": line.unit_price,
        })
    return rows


def check_po(po, company=None):
    if po.status != PurchaseOrder.Status.SENT:
        raise ValidationError({"purchase_order": f"{po.po_no} is {po.get_status_display().lower()}; goods are received against POs sent to the supplier."})


def check_receipt_lines(receipt_or_none, po, lines):
    for line in lines:
        pl = line["po_line"]
        if pl.order_id != po.id:
            raise ValidationError({"lines": f"“{pl.description}” is not on {po.po_no}."})
        limit = pl.quantity * (1 + OVER_RECEIPT_TOLERANCE) - received_so_far(pl, exclude_receipt=receipt_or_none)
        if line["received_qty"] > limit:
            raise ValidationError({"lines": f"“{pl.description}”: {line['received_qty']} is more than the PO allows "
                                             f"({q2(max(limit, ZERO))} {pl.unit} left including {int(OVER_RECEIPT_TOLERANCE * 100)}% tolerance)."})


def grn_actions(grn, user):
    return {
        GoodsReceipt.Status.DRAFT: ["edit", "submit", "delete"],
        GoodsReceipt.Status.RECEIVED: ["inspect"],
        GoodsReceipt.Status.INSPECTED: [],
    }[grn.status]


@transaction.atomic
def submit_grn(grn, user):
    grn = GoodsReceipt.objects.select_for_update().get(pk=grn.pk)
    if grn.status != GoodsReceipt.Status.DRAFT:
        raise Conflict("Only draft goods receipts can be submitted.")
    po = PurchaseOrder.objects.select_for_update().get(pk=grn.purchase_order_id)  # serialise receipts per PO
    check_po(po)
    lines = list(grn.lines.select_related("po_line"))
    if not lines:
        raise ValidationError({"lines": "Enter what was received."})
    check_receipt_lines(grn, po, [{"po_line": line.po_line, "received_qty": line.received_qty} for line in lines])
    grn.status, grn.submitted_at = GoodsReceipt.Status.RECEIVED, timezone.now()
    grn.save(update_fields=["status", "submitted_at", "updated_at"])
    log("grn", grn, "received", user, f"{len(lines)} lines from {grn.supplier.name}, awaiting inspection")
    return grn


@transaction.atomic
def inspect_grn(grn, user, results, notes=""):
    """results = [{"line": id, "accepted_qty": .., "rejected_qty": .., "remarks": ".."}] for every line.
    Accepted quantity goes into stock at the PO price."""
    grn = GoodsReceipt.objects.select_for_update().get(pk=grn.pk)
    if grn.status != GoodsReceipt.Status.RECEIVED:
        raise Conflict("Only received goods awaiting inspection can be inspected.")
    lines = {line.id: line for line in grn.lines.select_related("po_line", "material")}
    given = {int(r.get("line") or 0): r for r in results}
    if set(given) != set(lines):
        raise ValidationError({"results": "Give a result for every line."})
    rejected_notes = []
    for lid, line in lines.items():
        r = given[lid]
        try:
            accepted, rejected = Decimal(str(r.get("accepted_qty", 0) or 0)), Decimal(str(r.get("rejected_qty", 0) or 0))
        except ArithmeticError:
            raise ValidationError({"results": "Quantities must be numbers."}) from None
        if accepted < 0 or rejected < 0 or accepted + rejected != line.received_qty:
            raise ValidationError({"results": f"“{line.po_line.description}”: accepted + rejected must equal {line.received_qty} received."})
        remarks = str(r.get("remarks", "")).strip()
        if rejected > 0 and not remarks:
            raise ValidationError({"results": f"“{line.po_line.description}”: say why {rejected} {line.po_line.unit} was rejected."})
        line.accepted_qty, line.rejected_qty, line.remarks = accepted, rejected, remarks[:300]
        line.result = (GoodsReceiptLine.Result.PASSED if rejected == 0 else
                       GoodsReceiptLine.Result.FAILED if accepted == 0 else GoodsReceiptLine.Result.PARTIAL)
        line.save(update_fields=["accepted_qty", "rejected_qty", "remarks", "result"])
        if accepted > 0:
            stock = _locked_stock(line.material, grn.warehouse)
            _move(stock, accepted, MaterialMovement.Type.RECEIPT, user, unit_cost=line.po_line.unit_price,
                  grn_line=line, reference=grn.grn_no, note=f"{grn.purchase_order.po_no} · {grn.supplier.name}")
        if rejected:
            rejected_notes.append(f"{rejected} {line.po_line.unit} {line.po_line.description}")
    grn.status, grn.inspected_by, grn.inspected_at, grn.inspection_notes = GoodsReceipt.Status.INSPECTED, user, timezone.now(), notes
    grn.save(update_fields=["status", "inspected_by", "inspected_at", "inspection_notes", "updated_at"])
    log("grn", grn, "inspected", user,
        "All accepted" if not rejected_notes else "Rejected, return to supplier: " + "; ".join(rejected_notes))
    return grn


# ---------------------------------------------------------------- allocation

def _check_order(order):
    if order.status != OrderConfirmation.Status.CONFIRMED:
        raise Conflict("Stock is only allocated to confirmed orders.")


@transaction.atomic
def allocate(order, material, warehouse, quantity, user, requirement_line=None, note=""):
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError({"quantity": "Allocate more than zero."})
    _check_order(order)
    _check_warehouse(material, warehouse)
    if material.company_id != order.company_id:
        raise ValidationError({"material": "That material belongs to another company."})
    if requirement_line and requirement_line.requirement.order_id != order.id:
        raise ValidationError({"requirement_line": "That requirement line is for another order."})
    stock = _locked_stock(material, warehouse)
    if quantity > stock.available:
        raise ValidationError({"quantity": f"Only {stock.available} {material.unit} of {material} is free in {warehouse.name}."})
    stock.allocated += quantity
    stock.save(update_fields=["allocated", "updated_at"])
    alloc = MaterialAllocation.objects.create(
        company=order.company, material=material, warehouse=warehouse, order=order, requirement_line=requirement_line,
        quantity=quantity, note=note, created_by=user,
    )
    log("allocation", alloc, "allocated", user, f"{quantity} {material.unit} of {material} from {warehouse.name} to {order.oc_no}")
    return alloc


def _finish(alloc):
    if alloc.remaining == 0:
        alloc.status = MaterialAllocation.Status.ISSUED if alloc.issued_qty > 0 else MaterialAllocation.Status.RELEASED


def _locked_allocation(alloc):
    alloc = MaterialAllocation.objects.select_for_update().select_related("material", "warehouse", "order").get(pk=alloc.pk)
    if alloc.status != MaterialAllocation.Status.ACTIVE:
        raise Conflict(f"This allocation is already {alloc.get_status_display().lower()}.")
    return alloc


def _qty(value, alloc):
    qty = alloc.remaining if value in (None, "") else Decimal(str(value))
    if qty <= 0 or qty > alloc.remaining:
        raise ValidationError({"quantity": f"Give a quantity between 0 and {alloc.remaining} {alloc.material.unit}."})
    return qty


@transaction.atomic
def release_allocation(alloc, user, quantity=None):
    alloc = _locked_allocation(alloc)
    qty = _qty(quantity, alloc)
    stock = _locked_stock(alloc.material, alloc.warehouse)
    stock.allocated -= qty
    stock.save(update_fields=["allocated", "updated_at"])
    alloc.released_qty += qty
    _finish(alloc)
    alloc.save(update_fields=["released_qty", "status", "updated_at"])
    log("allocation", alloc, "released", user, f"{qty} {alloc.material.unit} back to free stock")
    return alloc


@transaction.atomic
def issue_allocation(alloc, user, quantity=None):
    """Issue allocated material to production: leaves the store."""
    alloc = _locked_allocation(alloc)
    qty = _qty(quantity, alloc)
    stock = _locked_stock(alloc.material, alloc.warehouse)
    stock.allocated -= qty
    _move(stock, -qty, MaterialMovement.Type.ISSUE, user, allocation=alloc, reference=alloc.order.oc_no,
          note=f"Issued to production for {alloc.order.oc_no}")
    alloc.issued_qty += qty
    _finish(alloc)
    alloc.save(update_fields=["issued_qty", "status", "updated_at"])
    log("allocation", alloc, "issued", user, f"{qty} {alloc.material.unit} to production")
    return alloc


def allocation_plan(requirement):
    """Per requirement line: matching material, what is allocated/issued for the order and what is free where."""
    order = requirement.order
    rows = []
    for line in requirement.lines.all():
        material = match_material(requirement.company, line.category, line.description, line.colour, line.unit)
        allocs = list(MaterialAllocation.objects.filter(order=order, requirement_line=line)) if order else []
        reserved = sum((a.remaining for a in allocs if a.status == MaterialAllocation.Status.ACTIVE), ZERO)
        issued = sum((a.issued_qty for a in allocs), ZERO)
        stock = list(MaterialStock.objects.filter(material=material).select_related("warehouse")) if material else []
        rows.append({
            "requirement_line": line.id, "category": line.category, "description": line.description, "colour": line.colour,
            "unit": line.unit, "required_qty": line.required_qty, "allocated_qty": reserved, "issued_qty": issued,
            "still_needed": max(line.required_qty - reserved - issued, ZERO),
            "material": material.id if material else None, "material_code": material.code if material else None,
            "stock": [{"warehouse": s.warehouse_id, "warehouse_name": s.warehouse.name, "on_hand": s.on_hand,
                       "available": s.available} for s in stock if s.on_hand > 0],
        })
    return rows


@transaction.atomic
def auto_allocate(requirement, user, warehouse=None):
    """Allocate free stock to every line that still needs material (preferred warehouse first)."""
    if not requirement.order_id:
        raise Conflict("This requirement is not for an order.")
    _check_order(requirement.order)
    made = []
    for row in allocation_plan(requirement):
        need = row["still_needed"]
        if need <= 0 or not row["material"]:
            continue
        material = Material.objects.get(pk=row["material"])
        stocks = MaterialStock.objects.filter(material=material, on_hand__gt=0).select_related("warehouse")
        stocks = sorted(stocks, key=lambda s: (warehouse is None or s.warehouse_id != warehouse.id, -s.available))
        for s in stocks:
            take = min(need, s.available)
            if take <= 0:
                continue
            made.append(allocate(requirement.order, material, s.warehouse, take, user,
                                 requirement_line_id_to_obj(row["requirement_line"]), note="Auto-allocated"))
            need -= take
            if need <= 0:
                break
    return made


def requirement_line_id_to_obj(line_id):
    from apps.procurement.models import RequirementLine
    return RequirementLine.objects.select_related("requirement").get(pk=line_id)


def stock_summary(company=None):
    qs = MaterialStock.objects.all()
    if company:
        qs = qs.filter(material__company=company)
    agg = qs.aggregate(value=Sum("value"))
    low = Material.objects.filter(reorder_level__gt=0)
    if company:
        low = low.filter(company=company)
    low_count = sum(1 for m in low.annotate(total=Sum("stock__on_hand")) if (m.total or 0) <= m.reorder_level)
    pending = GoodsReceipt.objects.filter(status=GoodsReceipt.Status.RECEIVED)
    if company:
        pending = pending.filter(company=company)
    return {"stock_value": agg["value"] or ZERO, "low_stock": low_count, "awaiting_inspection": pending.count(),
            "allocations_active": MaterialAllocation.objects.filter(status="active").filter(Q(company=company) if company else Q()).count()}
