"""Tests for Razorpay UPI QR payments. Razorpay itself is replaced with fakes — no network calls."""

import hashlib
import hmac
import json
import time
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.companies.models import Company
from apps.sales.models import Customer, Product, SalesOrder, SalesOrderItem

from .models import Invoice, Payment, UpiQrCode

KEYS = dict(RAZORPAY_KEY_ID="rzp_test_x", RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="whsec", RAZORPAY_QR_MINUTES=15)


def fake_qr(qr_id="qr_TEST1", amount_paise=118000):
    return {"id": qr_id, "entity": "qr_code", "image_url": f"https://rzp.io/i/{qr_id}", "status": "active",
            "payment_amount": amount_paise, "close_by": int(time.time()) + 900}


def fake_payment(pay_id="pay_ABC", amount_paise=118000, status="captured"):
    return {"id": pay_id, "entity": "payment", "amount": amount_paise, "currency": "INR", "status": status,
            "method": "upi", "vpa": "customer@ybl", "acquirer_data": {"rrn": "612345678901"},
            "created_at": int(time.time())}


@override_settings(**KEYS)
class UpiQrTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.client.force_authenticate(self.sales)
        company = Company.objects.create(name="Hazpo", code="A")
        customer = Customer.objects.create(company=company, name="Cust")
        product = Product.objects.create(company=company, sku="X", name="Valve", unit_price=Decimal("100"))
        order = SalesOrder.objects.create(company=company, customer=customer, order_date=date(2026, 3, 1), status="invoiced")
        SalesOrderItem.objects.create(order=order, product=product, quantity=10, unit_price=100, tax_rate=18)
        order.recalculate_totals()  # 1180.00
        self.order = order
        self.invoice = Invoice.objects.create(
            sales_order=order, company=company, customer=customer, invoice_date=date(2026, 3, 2),
            due_date=date(2026, 4, 1), subtotal=order.subtotal, tax_amount=order.tax_amount, total=order.total,
        )
        self.url = f"/api/invoices/{self.invoice.id}/upi-qr/"

    def make_qr(self, qr_id="qr_TEST1"):
        with mock.patch("apps.billing.razorpay.create_upi_qr", return_value=fake_qr(qr_id)) as create:
            res = self.client.post(self.url)
        return res, create

    def webhook(self, payment, qr_id="qr_TEST1", secret="whsec", event="qr_code.credited"):
        body = json.dumps({"entity": "event", "event": event, "payload": {
            "payment": {"entity": payment}, "qr_code": {"entity": {"id": qr_id}}}}).encode()
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.client.force_authenticate(None)  # Razorpay is not logged in
        return self.client.post("/api/razorpay/webhook/", body, content_type="application/json",
                                HTTP_X_RAZORPAY_SIGNATURE=sig)

    # --- creating the QR ---
    def test_create_qr_for_balance(self):
        res, create = self.make_qr()
        self.assertEqual(res.status_code, 201, res.data)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["amount_paise"], 118000)
        self.assertEqual(kwargs["description"], f"Invoice {self.invoice.invoice_no}")
        self.assertTrue(time.time() + 120 < kwargs["close_by"] <= time.time() + 7200)  # Razorpay: 2 min - 2 h
        self.assertEqual(res.data["image_url"], "https://rzp.io/i/qr_TEST1")
        self.assertEqual(res.data["status"], "active")

    def test_qr_uses_remaining_balance_after_part_payment(self):
        Payment.objects.create(invoice=self.invoice, payment_date=date(2026, 3, 3), amount=Decimal("180"))
        self.invoice.refresh_payment_status()
        _, create = self.make_qr()
        self.assertEqual(create.call_args.kwargs["amount_paise"], 100000)

    def test_new_qr_closes_the_previous_one(self):
        self.make_qr("qr_OLD")
        with mock.patch("apps.billing.razorpay.fetch_qr_payments", return_value=[]), \
             mock.patch("apps.billing.razorpay.close_qr") as close:
            with mock.patch("apps.billing.razorpay.create_upi_qr", return_value=fake_qr("qr_NEW")):
                self.client.post(self.url)
        close.assert_called_once_with("qr_OLD")
        self.assertEqual(UpiQrCode.objects.get(razorpay_qr_id="qr_OLD").status, "closed")

    def test_no_qr_for_paid_or_cancelled_invoice(self):
        self.invoice.status = Invoice.Status.CANCELLED
        self.invoice.save()
        res, create = self.make_qr()
        self.assertEqual(res.status_code, 400)
        create.assert_not_called()

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_not_configured(self):
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 400)
        self.assertIn("not set up", str(res.data))

    def test_razorpay_error_is_shown(self):
        from .razorpay import RazorpayError
        with mock.patch("apps.billing.razorpay.create_upi_qr", side_effect=RazorpayError("Razorpay error (401): Authentication failed")):
            res = self.client.post(self.url)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Authentication failed", str(res.data))

    # --- webhook ---
    def test_webhook_records_payment_and_marks_paid(self):
        self.make_qr()
        res = self.webhook(fake_payment())
        self.assertEqual(res.data["status"], "recorded")
        self.invoice.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.invoice.status, self.order.status), ("paid", "paid"))
        p = Payment.objects.get()
        self.assertEqual((p.amount, p.method, p.reference, p.gateway_payment_id), (Decimal("1180.00"), "upi", "612345678901", "pay_ABC"))
        self.assertIn("customer@ybl", p.notes)
        self.assertEqual(UpiQrCode.objects.get().status, "paid")

    def test_duplicate_webhook_records_once(self):
        self.make_qr()
        self.webhook(fake_payment())
        self.webhook(fake_payment())
        self.assertEqual(Payment.objects.count(), 1)

    def test_bad_signature_rejected(self):
        self.make_qr()
        res = self.webhook(fake_payment(), secret="wrong")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_missing_signature_rejected(self):
        self.client.force_authenticate(None)
        res = self.client.post("/api/razorpay/webhook/", {"event": "qr_code.credited"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_unknown_qr_and_other_events_ignored(self):
        self.make_qr()
        self.assertEqual(self.webhook(fake_payment(), qr_id="qr_SOMEONE_ELSE").data["status"], "ignored")
        self.assertEqual(self.webhook(fake_payment(), event="qr_code.closed").data["status"], "ignored")
        self.assertEqual(Payment.objects.count(), 0)

    def test_uncaptured_payment_not_recorded(self):
        self.make_qr()
        self.webhook(fake_payment(status="failed"))
        self.assertEqual(Payment.objects.count(), 0)

    def test_overpayment_flagged_for_review_not_recorded(self):
        self.make_qr()
        # meanwhile the customer paid ₹500 in cash at the counter
        Payment.objects.create(invoice=self.invoice, payment_date=date(2026, 3, 3), amount=Decimal("500"))
        self.invoice.refresh_payment_status()
        res = self.webhook(fake_payment())
        self.assertEqual(res.data["status"], "not_recorded")
        qr = UpiQrCode.objects.get()
        self.assertEqual(qr.status, "needs_review")
        self.assertIn("more than the balance", qr.review_note)
        self.assertEqual(Payment.objects.count(), 1)

    # --- checking from the app (no webhook needed) ---
    def test_status_check_records_payment(self):
        self.make_qr()
        with mock.patch("apps.billing.razorpay.fetch_qr_payments", return_value=[fake_payment()]):
            res = self.client.get(self.url)
        self.assertEqual((res.data["status"], res.data["invoice_status"]), ("paid", "paid"))
        # webhook arriving later does not double count
        self.webhook(fake_payment())
        self.assertEqual(Payment.objects.count(), 1)

    def test_status_check_waiting(self):
        self.make_qr()
        with mock.patch("apps.billing.razorpay.fetch_qr_payments", return_value=[]):
            res = self.client.get(self.url)
        self.assertEqual(res.data["status"], "active")

    def test_expired_qr_marked_closed(self):
        self.make_qr()
        UpiQrCode.objects.update(close_by=UpiQrCode.objects.get().created_at.replace(year=2020))
        with mock.patch("apps.billing.razorpay.fetch_qr_payments", return_value=[]):
            res = self.client.get(self.url)
        self.assertEqual(res.data["status"], "closed")

    def test_signature_helper_matches_razorpay_rule(self):
        from .razorpay import verify_webhook_signature
        body = b'{"a":1}'
        good = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(body, good))
        self.assertFalse(verify_webhook_signature(body + b" ", good))
