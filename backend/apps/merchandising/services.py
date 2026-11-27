"""
Workflow for cost sheets, quotations and order confirmations.
Every status change goes through a function here: it locks the row, checks the
transition, writes an ActivityLog entry and logs it.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.models import Buyer, CreditCheck
from apps.buyers.services import Conflict, is_manager

from .models import ActivityLog, CostSheet, OrderConfirmation, OrderConfirmationLine, Quotation

logger = logging.getLogger(__name__)


class CreditLimitExceeded(Conflict):
    default_code = "credit_limit_exceeded"


def log(doc_type, doc, action, user, note=""):
    ActivityLog.objects.create(doc_type=doc_type, doc_id=doc.pk, action=action, user=user, note=note)
    logger.info("%s %s %s user=%s", doc_type, doc.pk, action, getattr(user, "pk", None))


def history(doc_type, doc_id):
    return ActivityLog.objects.filter(doc_type=doc_type, doc_id=doc_id).select_related("user")


def _lock(model, obj):
    return model.objects.select_for_update().get(pk=obj.pk)


def require_approved_buyer(buyer):
    if buyer.status != Buyer.Status.APPROVED:
        raise ValidationError({"buyer": f"{buyer.legal_name} is not an approved buyer yet. Finish buyer onboarding first."})


def ensure_draft(doc, label):
    if doc.status != "draft":
        raise Conflict(f"This {label} is {doc.get_status_display().lower()} and can no longer be edited.")


# ---------------------------------------------------------------- cost sheets

def cost_sheet_actions(sheet, user):
    actions = []
    if sheet.status == CostSheet.Status.DRAFT:
        actions += ["edit", "delete"]
        if is_manager(user):
            actions.append("approve")
    elif is_manager(user) and not cost_sheet_in_use(sheet):
        actions.append("reopen")
    if sheet.status == CostSheet.Status.APPROVED:
        actions.append("quote")
    actions.append("copy")
    return actions


def cost_sheet_in_use(sheet):
    """True when a sent/accepted quotation or any order uses this cost sheet."""
    return sheet.order_lines.exists() or sheet.quotation_lines.exclude(
        quotation__status__in=[Quotation.Status.DRAFT, Quotation.Status.CANCELLED, Quotation.Status.REJECTED]
    ).exists()


@transaction.atomic
def approve_cost_sheet(sheet, user):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can approve cost sheets.")
    sheet = _lock(CostSheet, sheet)
    if sheet.status == CostSheet.Status.APPROVED:
        return sheet
    if not sheet.lines.exists() or sheet.fob_price <= 0:
        raise ValidationError({"lines": "Add cost lines before approving."})
    sheet.status = CostSheet.Status.APPROVED
    sheet.approved_by = user
    sheet.approved_at = timezone.now()
    sheet.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log("cost_sheet", sheet, "approved", user, f"FOB {sheet.fob_price} {sheet.currency}")
    return sheet


@transaction.atomic
def reopen_cost_sheet(sheet, user):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can reopen cost sheets.")
    sheet = _lock(CostSheet, sheet)
    if sheet.status != CostSheet.Status.APPROVED:
        raise Conflict("Only approved cost sheets can be reopened.")
    if cost_sheet_in_use(sheet):
        raise Conflict("This cost sheet is used on a quotation sent to the buyer or an order. Copy it instead.")
    sheet.status = CostSheet.Status.DRAFT
    sheet.approved_by = None
    sheet.approved_at = None
    sheet.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log("cost_sheet", sheet, "reopened", user)
    return sheet


@transaction.atomic
def copy_cost_sheet(sheet, user):
    """New draft with the same lines, e.g. for a revised costing or a similar style."""
    lines = list(sheet.lines.all())
    new = CostSheet.objects.create(
        company=sheet.company, buyer=sheet.buyer, style_no=sheet.style_no, style_name=sheet.style_name,
        category=sheet.category, fabric_composition=sheet.fabric_composition, gsm=sheet.gsm,
        size_range=sheet.size_range, quantity=sheet.quantity, currency=sheet.currency,
        overhead_pct=sheet.overhead_pct, margin_pct=sheet.margin_pct, commission_pct=sheet.commission_pct,
        notes=sheet.notes, created_by=user,
    )
    for line in lines:
        line.pk = None
        line.cost_sheet = new
        line.save()
    new.recalculate()
    log("cost_sheet", new, "created", user, f"Copied from {sheet.cost_no}")
    return new


# ---------------------------------------------------------------- quotations

def quotation_actions(quote, user):
    s = Quotation.Status
    actions = []
    if quote.status == s.DRAFT:
        actions += ["edit", "send", "cancel"]
    elif quote.status == s.SENT:
        actions += ["accept", "reject", "reopen", "cancel"]
    elif quote.status == s.ACCEPTED:
        actions.append("view_order" if hasattr(quote, "order_confirmation") else "create_order")
    return actions


def _check_not_expired(quote):
    if quote.valid_until < timezone.localdate():
        raise Conflict(f"This quotation expired on {quote.valid_until:%d %b %Y}. Reopen it and update the validity date.")


@transaction.atomic
def send_quotation(quote, user):
    quote = _lock(Quotation, quote)
    if quote.status != Quotation.Status.DRAFT:
        raise Conflict("Only draft quotations can be sent.")
    require_approved_buyer(quote.buyer)
    if not quote.lines.exists():
        raise ValidationError({"lines": "Add at least one style before sending."})
    _check_not_expired(quote)
    quote.status = Quotation.Status.SENT
    quote.sent_at = timezone.now()
    quote.save(update_fields=["status", "sent_at", "updated_at"])
    log("quotation", quote, "sent", user, f"{quote.total_quantity} pcs, {quote.currency} {quote.total_amount}")
    return quote


@transaction.atomic
def reopen_quotation(quote, user):
    quote = _lock(Quotation, quote)
    if quote.status != Quotation.Status.SENT:
        raise Conflict("Only sent quotations can be reopened for changes.")
    quote.status = Quotation.Status.DRAFT
    quote.save(update_fields=["status", "updated_at"])
    log("quotation", quote, "reopened", user)
    return quote


@transaction.atomic
def accept_quotation(quote, user, note=""):
    quote = _lock(Quotation, quote)
    if quote.status == Quotation.Status.ACCEPTED:
        return quote
    if quote.status != Quotation.Status.SENT:
        raise Conflict("Only quotations sent to the buyer can be accepted.")
    _check_not_expired(quote)
    quote.status = Quotation.Status.ACCEPTED
    quote.accepted_at = timezone.now()
    quote.save(update_fields=["status", "accepted_at", "updated_at"])
    log("quotation", quote, "accepted", user, note or "Buyer accepted")
    return quote


@transaction.atomic
def reject_quotation(quote, user, reason):
    if not reason:
        raise ValidationError({"reason": "Give the buyer's reason, e.g. price too high."})
    quote = _lock(Quotation, quote)
    if quote.status != Quotation.Status.SENT:
        raise Conflict("Only quotations sent to the buyer can be rejected.")
    quote.status = Quotation.Status.REJECTED
    quote.reject_reason = reason
    quote.save(update_fields=["status", "reject_reason", "updated_at"])
    log("quotation", quote, "rejected", user, reason)
    return quote


@transaction.atomic
def cancel_quotation(quote, user, reason=""):
    quote = _lock(Quotation, quote)
    if quote.status not in (Quotation.Status.DRAFT, Quotation.Status.SENT):
        raise Conflict("Only draft or sent quotations can be cancelled.")
    quote.status = Quotation.Status.CANCELLED
    quote.save(update_fields=["status", "updated_at"])
    log("quotation", quote, "cancelled", user, reason)
    return quote


@transaction.atomic
def create_order(quote, user):
    """Order confirmation from an accepted quotation. Calling it again returns the same order."""
    quote = _lock(Quotation, quote)
    existing = OrderConfirmation.objects.filter(quotation=quote).first()
    if existing:
        return existing, False
    if quote.status != Quotation.Status.ACCEPTED:
        raise Conflict("Only accepted quotations can become orders.")
    order = OrderConfirmation.objects.create(
        company=quote.company, buyer=quote.buyer, quotation=quote, currency=quote.currency,
        incoterm=quote.incoterm, payment_terms=quote.payment_terms, delivery_port=quote.delivery_port,
        ship_date=quote.delivery_date,
    )
    OrderConfirmationLine.objects.bulk_create([
        OrderConfirmationLine(
            order=order, cost_sheet_id=line.cost_sheet_id, style_no=line.style_no, description=line.description,
            quantity=line.quantity, unit_price=line.unit_price, amount=line.amount,
        )
        for line in quote.lines.all()
    ])
    order.recalculate()
    log("order", order, "created", user, f"From quotation {quote.quote_no}")
    return order, True


# ---------------------------------------------------------------- orders

def latest_passed_credit(buyer):
    return buyer.credit_checks.filter(result=CreditCheck.Result.PASS).order_by("-checked_at", "-id").first()


def credit_position(order):
    """How this order fits in the buyer's credit limit (confirmed orders in the same currency count)."""
    credit = latest_passed_credit(order.buyer)
    confirmed = OrderConfirmation.objects.filter(
        buyer=order.buyer, status=OrderConfirmation.Status.CONFIRMED, currency=order.currency
    ).exclude(pk=order.pk)
    exposure = confirmed.aggregate(t=Sum("total_amount"))["t"] or Decimal("0")
    this_order = order.total_amount if order.status != OrderConfirmation.Status.CANCELLED else Decimal("0")
    if credit is None:
        return {
            "has_limit": False, "limit": None, "currency": order.currency, "currency_matches": False,
            "exposure": exposure, "this_order": this_order, "after_order": exposure + this_order,
            "available": None, "within_limit": False, "payment_terms": None,
        }
    matches = credit.currency == order.currency
    after = exposure + this_order
    return {
        "has_limit": True, "limit": credit.approved_limit, "currency": credit.currency, "currency_matches": matches,
        "exposure": exposure, "this_order": this_order, "after_order": after,
        "available": credit.approved_limit - exposure if matches else None,
        "within_limit": matches and after <= credit.approved_limit,
        "payment_terms": credit.payment_terms,
    }


def order_actions(order, user):
    s = OrderConfirmation.Status
    actions = []
    if order.status == s.DRAFT:
        actions += ["edit", "confirm", "cancel"]
    elif order.status == s.CONFIRMED and is_manager(user):
        actions.append("cancel")
    return actions


@transaction.atomic
def confirm_order(order, user, override_reason=""):
    order = _lock(OrderConfirmation, order)
    if order.status == OrderConfirmation.Status.CONFIRMED:
        return order
    if order.status != OrderConfirmation.Status.DRAFT:
        raise Conflict("Only draft orders can be confirmed.")
    require_approved_buyer(order.buyer)
    missing = {}
    if not order.buyer_po_no:
        missing["buyer_po_no"] = "Enter the buyer's PO number."
    if not order.ship_date:
        missing["ship_date"] = "Enter the agreed shipment date."
    if not order.lines.exists():
        missing["lines"] = "The order has no styles."
    if missing:
        raise ValidationError(missing)

    # Lock the buyer so two orders can't both squeeze into the same credit at once.
    Buyer.objects.select_for_update().get(pk=order.buyer_id)
    credit = credit_position(order)
    override = False
    if not credit["within_limit"]:
        if not credit["has_limit"]:
            problem = "The buyer has no approved credit limit."
        elif not credit["currency_matches"]:
            problem = f"The credit limit is in {credit['currency']} but this order is in {order.currency}."
        else:
            problem = (
                f"This order takes the buyer to {credit['after_order']} {order.currency}, "
                f"over the credit limit of {credit['limit']} {credit['currency']}."
            )
        if not (is_manager(user) and override_reason):
            hint = " A manager can confirm it with a reason." if not is_manager(user) else " Give a reason to confirm anyway."
            raise CreditLimitExceeded(problem + hint)
        override = True

    order.status = OrderConfirmation.Status.CONFIRMED
    order.confirmed_by = user
    order.confirmed_at = timezone.now()
    order.credit_override = override
    order.override_reason = override_reason if override else ""
    order.save(update_fields=[
        "status", "confirmed_by", "confirmed_at", "credit_override", "override_reason", "updated_at",
    ])
    note = f"PO {order.buyer_po_no}, {order.total_quantity} pcs, {order.currency} {order.total_amount}"
    if override:
        note += f". Credit limit overridden: {override_reason}"
    log("order", order, "confirmed", user, note)
    return order


@transaction.atomic
def cancel_order(order, user, reason):
    if not reason:
        raise ValidationError({"reason": "Give a reason for cancelling."})
    order = _lock(OrderConfirmation, order)
    if order.status == OrderConfirmation.Status.CANCELLED:
        raise Conflict("This order is already cancelled.")
    if order.status == OrderConfirmation.Status.CONFIRMED and not is_manager(user):
        raise PermissionDenied("Only managers and admins can cancel a confirmed order.")
    order.status = OrderConfirmation.Status.CANCELLED
    order.cancel_reason = reason
    order.save(update_fields=["status", "cancel_reason", "updated_at"])
    log("order", order, "cancelled", user, reason)
    return order
