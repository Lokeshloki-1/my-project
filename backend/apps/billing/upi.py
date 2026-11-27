"""
UPI QR payments through Razorpay.

Flow:
  1. create_qr_for_invoice(): ask Razorpay for a one-time QR for the invoice balance.
  2. The customer scans it with PhonePe / Google Pay / Paytm / any UPI app and pays.
  3. Razorpay tells us in one of two ways — both end in record_gateway_payment(), which is idempotent:
     - the qr_code.credited webhook (instant; needs a public URL), or
     - sync_qr(), which asks Razorpay for the QR's payments (used while the QR is on screen; works locally).
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import razorpay
from .models import Invoice, Payment, UpiQrCode

log = logging.getLogger(__name__)
OPEN_STATUSES = (Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID)


def create_qr_for_invoice(invoice, user=None):
    if not razorpay.is_configured():
        raise ValidationError("Razorpay is not set up. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to backend/.env.")
    if invoice.status not in OPEN_STATUSES or invoice.balance <= 0:
        raise ValidationError("This invoice has nothing left to pay.")

    # Only one QR per invoice should be payable at a time, or the customer could pay twice.
    for old in invoice.upi_qr_codes.filter(status=UpiQrCode.Status.ACTIVE):
        sync_qr(old)  # a payment may have just arrived on it
        old.refresh_from_db()
        if old.status == UpiQrCode.Status.ACTIVE:
            try:
                razorpay.close_qr(old.razorpay_qr_id)
            except razorpay.RazorpayError as exc:
                log.warning("Could not close QR %s: %s", old.razorpay_qr_id, exc)
            old.status = UpiQrCode.Status.CLOSED
            old.save(update_fields=["status", "updated_at"])
    invoice.refresh_from_db()
    if invoice.status not in OPEN_STATUSES:
        raise ValidationError("This invoice was just paid.")

    minutes = min(max(settings.RAZORPAY_QR_MINUTES, 3), 120)  # Razorpay allows 2 min - 2 h
    close_by = timezone.now() + timedelta(minutes=minutes)
    amount = invoice.balance
    try:
        qr = razorpay.create_upi_qr(
            amount_paise=int(amount * 100),
            name=invoice.company.name,
            description=f"Invoice {invoice.invoice_no}",
            close_by=int(close_by.timestamp()),
            notes={"invoice_no": invoice.invoice_no, "invoice_id": str(invoice.id)},
        )
    except razorpay.RazorpayError as exc:
        raise ValidationError(str(exc))
    return UpiQrCode.objects.create(
        invoice=invoice, razorpay_qr_id=qr["id"], image_url=qr["image_url"], amount=amount,
        close_by=datetime.fromtimestamp(int(qr.get("close_by") or close_by.timestamp()), tz=dt_timezone.utc),
        created_by=user,
    )


def record_gateway_payment(qr, payment):
    """
    Record one Razorpay payment entity against the QR's invoice. Safe to call many times for the same payment.
    Returns the Payment, or None if it was not recorded (not captured, or needs a person to look at it).
    """
    if payment.get("status") != "captured":
        return None
    gateway_id = payment["id"]
    amount = (Decimal(payment["amount"]) / 100).quantize(Decimal("0.01"))
    try:
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=qr.invoice_id)
            qr = UpiQrCode.objects.select_for_update().get(pk=qr.pk)
            existing = Payment.objects.filter(gateway_payment_id=gateway_id).first()
            if existing:
                return existing

            problem = None
            if payment.get("currency", "INR") != "INR":
                problem = f"Payment {gateway_id} is in {payment.get('currency')}, not INR."
            elif invoice.status not in OPEN_STATUSES:
                problem = f"Payment {gateway_id} of ₹{amount} arrived but invoice {invoice.invoice_no} is {invoice.status}."
            elif amount > invoice.balance:
                problem = (f"Payment {gateway_id} of ₹{amount} is more than the balance ₹{invoice.balance} "
                           f"(was part of it paid another way?).")
            if problem:
                # The customer's money HAS reached Razorpay; a person must apply or refund it.
                qr.status = UpiQrCode.Status.NEEDS_REVIEW
                qr.review_note = problem
                qr.save(update_fields=["status", "review_note", "updated_at"])
                log.warning(problem)
                return None

            paid_at = datetime.fromtimestamp(int(payment.get("created_at") or timezone.now().timestamp()), tz=dt_timezone.utc)
            rrn = (payment.get("acquirer_data") or {}).get("rrn")
            record = Payment.objects.create(
                invoice=invoice,
                payment_date=max(timezone.localdate(paid_at), invoice.invoice_date),
                amount=amount,
                method=Payment.Method.UPI,
                reference=rrn or gateway_id,
                notes=f"Razorpay UPI QR {qr.razorpay_qr_id}, payment {gateway_id}"
                      + (f", from {payment['vpa']}" if payment.get("vpa") else ""),
                gateway_payment_id=gateway_id,
            )
            invoice.refresh_payment_status()
            qr.status = UpiQrCode.Status.PAID
            qr.save(update_fields=["status", "updated_at"])
            return record
    except IntegrityError:
        # Another request recorded the same payment at the same moment.
        return Payment.objects.filter(gateway_payment_id=gateway_id).first()


def sync_qr(qr):
    """Ask Razorpay for payments on an active QR and record them. Also marks expired QRs as closed."""
    if qr.status != UpiQrCode.Status.ACTIVE or not razorpay.is_configured():
        return qr
    try:
        payments = razorpay.fetch_qr_payments(qr.razorpay_qr_id)
    except razorpay.RazorpayError as exc:
        log.warning("Could not check QR %s: %s", qr.razorpay_qr_id, exc)
        return qr
    for p in payments:
        record_gateway_payment(qr, p)
    qr.refresh_from_db()
    if qr.status == UpiQrCode.Status.ACTIVE and timezone.now() > qr.close_by:
        qr.status = UpiQrCode.Status.CLOSED
        qr.save(update_fields=["status", "updated_at"])
    return qr


def handle_webhook(event):
    """Process a verified Razorpay webhook event. Unknown events and QR codes are ignored."""
    if event.get("event") != "qr_code.credited":
        return "ignored"
    payload = event.get("payload") or {}
    qr_id = ((payload.get("qr_code") or {}).get("entity") or {}).get("id")
    payment = (payload.get("payment") or {}).get("entity")
    qr = UpiQrCode.objects.filter(razorpay_qr_id=qr_id).first()
    if not qr or not payment:
        return "ignored"
    return "recorded" if record_gateway_payment(qr, payment) else "not_recorded"
