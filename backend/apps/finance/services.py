import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.services import Conflict, is_manager
from apps.exports.models import ExportShipment
from apps.buyers.models import Buyer
from apps.exports.services import invoice_lines
from apps.merchandising.models import OrderConfirmation
from apps.merchandising.services import latest_passed_credit
from apps.stores.models import MaterialAllocation, MaterialMovement, MaterialStock

from .models import ExportInvoice, ExportReceipt, OrderExpense, q2

logger = logging.getLogger(__name__)
ZERO = Decimal("0")
S = ExportInvoice.Status

# Days from invoice (≈ B/L) date until the buyer is due to pay.
DUE_DAYS = {"advance": 0, "lc_sight": 7, "lc_usance": 60, "tt_30": 30, "tt_60": 60, "tt_90": 90, "da": 60, "dp": 15}
CONVERSION_LINES = ("cmt", "washing", "print_embroidery", "testing", "packing")
BUCKETS = [("not_due", "Not due"), ("d1_30", "1–30 days"), ("d31_60", "31–60 days"), ("d61_90", "61–90 days"), ("d90_plus", "Over 90 days")]


def _refresh(invoice):
    agg = invoice.receipts.aggregate(r=Sum("amount"), c=Sum("bank_charges"))
    invoice.amount_received, invoice.bank_charges = agg["r"] or ZERO, agg["c"] or ZERO
    if invoice.status != S.CANCELLED:
        invoice.status = S.PAID if invoice.balance <= 0 else S.PARTIALLY_PAID if invoice.amount_received > 0 else S.OPEN
    invoice.save(update_fields=["amount_received", "bank_charges", "status", "amount_inr", "updated_at"])


@transaction.atomic
def create_invoice(shipment, user, exchange_rate, invoice_date=None):
    """Sales invoice for a shipped export shipment. Calling it again returns the existing invoice."""
    shipment = ExportShipment.objects.select_for_update(of=("self",)).select_related("order__buyer").get(pk=shipment.pk)
    existing = ExportInvoice.objects.filter(shipment=shipment).first()
    if existing:
        return existing, False
    if shipment.status not in (ExportShipment.Status.SHIPPED, ExportShipment.Status.DELIVERED):
        raise Conflict("Invoices are raised for shipments that have shipped.")
    rate = Decimal(str(exchange_rate or 0))
    if rate <= 0:
        raise ValidationError({"exchange_rate": "Give the exchange rate (INR per unit), e.g. from the shipping bill."})
    lines = invoice_lines(shipment)
    amount = sum((line["amount"] for line in lines), ZERO)
    if amount <= 0:
        raise ValidationError({"detail": "The shipment has no invoiced value."})
    order = shipment.order
    date = invoice_date or shipment.invoice_date or shipment.on_board_date or timezone.localdate()
    inv = ExportInvoice.objects.create(
        company=shipment.company, shipment=shipment, order=order, buyer=order.buyer, invoice_no=shipment.invoice_no,
        invoice_date=date, currency=order.currency, amount=amount, exchange_rate=rate, payment_terms=order.payment_terms,
        due_date=date + timedelta(days=DUE_DAYS.get(order.payment_terms, 30)), created_by=user,
    )
    logger.info("export_invoice %s created amount=%s %s", inv.pk, amount, inv.currency)
    return inv, True


def invoice_actions(inv, user):
    if inv.status == S.CANCELLED:
        return []
    actions = ["record_receipt"] if inv.balance > 0 else []
    if not inv.receipts.exists() and is_manager(user):
        actions.append("cancel")
    return actions


@transaction.atomic
def record_receipt(invoice, user, data):
    inv = ExportInvoice.objects.select_for_update().get(pk=invoice.pk)
    if inv.status == S.CANCELLED:
        raise Conflict("This invoice is cancelled.")
    amount, charges = Decimal(str(data["amount"])), Decimal(str(data.get("bank_charges") or 0))
    if amount + charges > inv.balance:
        raise ValidationError({"amount": f"Amount + bank charges ({amount + charges}) is more than the balance {inv.balance} {inv.currency}."})
    if data["received_on"] > timezone.localdate():
        raise ValidationError({"received_on": "The date can't be in the future."})
    receipt = ExportReceipt.objects.create(
        invoice=inv, received_on=data["received_on"], amount=amount, bank_charges=charges, exchange_rate=data["exchange_rate"],
        method=data.get("method", ExportReceipt.Method.TT), bank_reference=data.get("bank_reference", ""),
        note=data.get("note", ""), created_by=user,
    )
    _refresh(inv)
    logger.info("export_receipt %s on invoice %s amount=%s", receipt.pk, inv.pk, amount)
    return receipt


@transaction.atomic
def delete_receipt(receipt, user):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can delete a receipt.")
    inv = ExportInvoice.objects.select_for_update().get(pk=receipt.invoice_id)
    receipt.delete()
    _refresh(inv)
    return inv


@transaction.atomic
def cancel_invoice(invoice, user, reason):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can cancel an invoice.")
    if not reason:
        raise ValidationError({"reason": "Give a reason for cancelling."})
    inv = ExportInvoice.objects.select_for_update().get(pk=invoice.pk)
    if inv.receipts.exists():
        raise Conflict("Payments are recorded against this invoice; delete them first.")
    inv.status, inv.cancel_reason = S.CANCELLED, reason
    inv.save(update_fields=["status", "cancel_reason", "updated_at"])
    return inv


# ---------------------------------------------------------------- receivables

def _bucket(days_overdue):
    if days_overdue <= 0:
        return "not_due"
    if days_overdue <= 30:
        return "d1_30"
    if days_overdue <= 60:
        return "d31_60"
    return "d61_90" if days_overdue <= 90 else "d90_plus"


def ageing(as_of=None, company=None):
    as_of = as_of or timezone.localdate()
    invoices = ExportInvoice.objects.filter(status__in=[S.OPEN, S.PARTIALLY_PAID]).select_related("buyer")
    if company:
        invoices = invoices.filter(company=company)
    buyers, rows, totals = {}, [], {k: ZERO for k, _ in BUCKETS}
    for inv in invoices:
        overdue = (as_of - inv.due_date).days
        bucket = _bucket(overdue)
        balance_inr = q2(inv.balance * inv.exchange_rate)
        rows.append({"invoice": inv.id, "invoice_no": inv.invoice_no, "buyer": inv.buyer_id, "buyer_name": inv.buyer.legal_name,
                     "invoice_date": inv.invoice_date, "due_date": inv.due_date, "days_overdue": max(overdue, 0), "bucket": bucket,
                     "currency": inv.currency, "balance": inv.balance, "balance_inr": balance_inr})
        b = buyers.setdefault(inv.buyer_id, {"buyer": inv.buyer_id, "buyer_name": inv.buyer.legal_name, "currency": inv.currency,
                                             "balance": ZERO, "balance_inr": ZERO, **{k: ZERO for k, _ in BUCKETS}})
        b["balance"] += inv.balance
        b["balance_inr"] += balance_inr
        b[bucket] += balance_inr
        totals[bucket] += balance_inr
    for b in buyers.values():
        credit = latest_passed_credit(Buyer.objects.get(pk=b["buyer"]))
        b["credit_limit"] = credit.approved_limit if credit else None
        b["credit_currency"] = credit.currency if credit else None
        b["over_limit"] = bool(credit and credit.currency == b["currency"] and b["balance"] > credit.approved_limit)
    return {"as_of": as_of, "buckets": [{"key": k, "label": l} for k, l in BUCKETS],
            "totals": totals, "total_inr": sum(totals.values(), ZERO),
            "overdue_inr": sum((v for k, v in totals.items() if k != "not_due"), ZERO),
            "by_buyer": sorted(buyers.values(), key=lambda b: -b["balance_inr"]),
            "invoices": sorted(rows, key=lambda r: -r["days_overdue"])}


# ---------------------------------------------------------------- profit

def _avg_cost(allocation):
    stock = MaterialStock.objects.filter(material=allocation.material, warehouse=allocation.warehouse).first()
    return stock.average_cost if stock else ZERO


def order_profit(order):
    invoices = [i for i in order.export_invoices.all() if i.status != S.CANCELLED]
    revenue = sum((i.amount for i in invoices), ZERO)
    revenue_inr = sum((i.amount_inr for i in invoices), ZERO)
    rate = (revenue_inr / revenue) if revenue else None
    receipts = [r for i in invoices for r in i.receipts.all()]
    bank_charges_inr = q2(sum((r.bank_charges * r.invoice.exchange_rate for r in receipts), ZERO))
    fx = sum((r.exchange_gain_loss_inr for r in receipts), ZERO)

    issues = MaterialMovement.objects.filter(movement_type=MaterialMovement.Type.ISSUE, allocation__order=order).select_related(
        "allocation__requirement_line")

    shipped = {}
    for inv in invoices:
        for line in invoice_lines(inv.shipment):
            shipped[line["style_no"]] = shipped.get(line["style_no"], 0) + line["pcs"]
    conversion, planned_cost, planned_revenue, styles = ZERO, ZERO, ZERO, []
    for line in order.lines.select_related("cost_sheet").prefetch_related("cost_sheet__lines"):
        sheet = line.cost_sheet
        conv_pc = sum((cl.amount for cl in sheet.lines.all() if cl.category in CONVERSION_LINES), ZERO)
        pcs = shipped.get(line.style_no, 0)
        conversion += conv_pc * pcs
        planned_cost += sheet.total_cost * line.quantity
        planned_revenue += line.unit_price * line.quantity
        styles.append({"style_no": line.style_no, "ordered": line.quantity, "shipped": pcs, "price": line.unit_price,
                       "cost_per_pc": sheet.total_cost, "conversion_per_pc": q2(conv_pc)})
    conversion_inr = q2(conversion * rate) if rate else ZERO
    # Match material cost to what was sold, per style: each issue goes to the styles its requirement line
    # serves (split by order quantity), then counts in proportion to that style's shipped pieces.
    ordered = {st["style_no"]: st["ordered"] for st in styles}
    issued_by_style = {k: ZERO for k in ordered}
    for m in issues:
        value = -m.quantity * (m.unit_cost or ZERO)
        rl = m.allocation.requirement_line if m.allocation_id else None
        targets = [x.strip() for x in rl.styles.split(",") if x.strip() in ordered] if rl and rl.styles else []
        targets = targets or list(ordered)
        weight = sum(ordered[t] for t in targets) or 1
        for t in targets:
            issued_by_style[t] += value * ordered[t] / weight
    materials_issued_inr = q2(sum(issued_by_style.values(), ZERO))
    materials_inr = q2(sum((v * min(Decimal(shipped.get(k, 0)) / Decimal(ordered[k]), Decimal("1")) for k, v in issued_by_style.items()
                            if ordered[k]), ZERO))
    for st in styles:
        st["materials_issued_inr"] = q2(issued_by_style.get(st["style_no"], ZERO))
    ordered_pcs, shipped_pcs = sum(ordered.values()), sum(min(shipped.get(k, 0), v) for k, v in ordered.items())
    warnings = []
    # Allocated-but-not-issued material only matters for styles that have shipped.
    shipped_styles = {k for k in ordered if shipped.get(k)}
    pending_value = ZERO
    for a in MaterialAllocation.objects.filter(order=order, status=MaterialAllocation.Status.ACTIVE).select_related("material", "requirement_line"):
        rl = a.requirement_line
        targets = [x.strip() for x in rl.styles.split(",") if x.strip() in ordered] if rl and rl.styles else []
        targets = targets or list(ordered)
        weight = sum(ordered[t] for t in targets) or 1
        pending_value += a.remaining * _avg_cost(a) * sum(ordered[t] for t in targets if t in shipped_styles) / weight
    pending_value = q2(pending_value)
    if shipped_pcs and pending_value > 0:
        warnings.append(f"Material worth about ₹{pending_value:,.0f} is allocated to this order but not issued to production yet, "
                        "so it isn't counted as cost — profit is overstated until it is issued.")
    if shipped_pcs and not issues.exists():
        warnings.append("No material has been issued to production for this order, so material cost is 0.")
    uninvoiced = [s.shipment_no for s in order.export_shipments.filter(status__in=["shipped", "delivered"], export_invoice__isnull=True)]
    if uninvoiced:
        warnings.append(f"Shipped but not invoiced yet: {', '.join(uninvoiced)}.")
    share = (Decimal(shipped_pcs) / Decimal(ordered_pcs)) if ordered_pcs else ZERO
    expenses = list(order.expenses.all())
    expenses_inr = sum((e.amount_inr for e in expenses), ZERO)
    by_cat = {}
    for e in expenses:
        by_cat[e.get_category_display()] = by_cat.get(e.get_category_display(), ZERO) + e.amount_inr
    cost_inr = materials_inr + conversion_inr + expenses_inr + bank_charges_inr
    profit = q2(revenue_inr - cost_inr + fx)
    planned_margin = q2((planned_revenue - planned_cost) / planned_revenue * 100) if planned_revenue else None
    return {
        "order": order.id, "oc_no": order.oc_no, "buyer_name": order.buyer.legal_name, "currency": order.currency,
        "order_value": planned_revenue, "invoiced": revenue, "invoiced_inr": revenue_inr, "invoice_rate": q2(rate) if rate else None,
        "received_inr": sum((r.amount_inr for r in receipts), ZERO),
        "shipped_pcs": shipped_pcs, "ordered_pcs": ordered_pcs, "shipped_share_pct": q2(share * 100),
        "materials_issued_inr": materials_issued_inr, "materials_in_wip_inr": materials_issued_inr - materials_inr,
        "costs": {"materials_inr": materials_inr, "conversion_inr": conversion_inr, "expenses_inr": expenses_inr,
                  "bank_charges_inr": bank_charges_inr, "total_inr": cost_inr, "expenses_by_category": by_cat},
        "exchange_gain_loss_inr": fx, "profit_inr": profit,
        "margin_pct": q2(profit / revenue_inr * 100) if revenue_inr else None, "planned_margin_pct": planned_margin,
        "styles": styles, "warnings": warnings,
    }


def summary(company=None):
    today = timezone.localdate()
    inv = ExportInvoice.objects.exclude(status=S.CANCELLED)
    rec = ExportReceipt.objects.all()
    if company:
        inv, rec = inv.filter(company=company), rec.filter(invoice__company=company)
    open_inv = [i for i in inv.filter(status__in=[S.OPEN, S.PARTIALLY_PAID])]
    month = rec.filter(received_on__year=today.year, received_on__month=today.month)
    return {
        "receivable_inr": q2(sum((i.balance * i.exchange_rate for i in open_inv), ZERO)),
        "overdue_inr": q2(sum((i.balance * i.exchange_rate for i in open_inv if i.due_date < today), ZERO)),
        "overdue_invoices": sum(1 for i in open_inv if i.due_date < today),
        "invoiced_this_month_inr": inv.filter(invoice_date__year=today.year, invoice_date__month=today.month).aggregate(t=Sum("amount_inr"))["t"] or ZERO,
        "collected_this_month_inr": month.aggregate(t=Sum("amount_inr"))["t"] or ZERO,
        "exchange_gain_loss_inr": rec.aggregate(t=Sum("exchange_gain_loss_inr"))["t"] or ZERO,
        "shipped_not_invoiced": ExportShipment.objects.filter(status__in=["shipped", "delivered"], export_invoice__isnull=True)
                                .filter(**({"company": company} if company else {})).count(),
    }


def orders_with_money(company=None):
    qs = OrderConfirmation.objects.filter(status=OrderConfirmation.Status.CONFIRMED).select_related("buyer").prefetch_related(
        "export_invoices__receipts", "export_invoices__shipment", "expenses")
    if company:
        qs = qs.filter(company=company)
    return qs

