from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.companies.models import Company
from apps.sales.models import Customer, Product, SalesOrder, SalesOrderItem

from .models import Invoice
from .pdf import amount_in_words, indian_number


class BillingApiTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.accountant = User.objects.create_user("acc", password="pass12345!", role=User.Role.ACCOUNTANT)
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.client.force_authenticate(self.accountant)
        self.company = Company.objects.create(name="Hazpo & Co <Test>", code="A")
        self.customer = Customer.objects.create(company=self.company, name="Cust <b>&</b>")
        product = Product.objects.create(company=self.company, sku="X", name="Valve", unit_price=Decimal("100"), tax_rate=Decimal("18"))
        self.order = SalesOrder.objects.create(
            company=self.company, customer=self.customer, order_date=date(2026, 3, 1), status="confirmed"
        )
        SalesOrderItem.objects.create(order=self.order, product=product, quantity=10, unit_price=100, tax_rate=18)
        self.order.recalculate_totals()  # total 1180.00

    def _invoice(self, **extra):
        body = {"sales_order": self.order.id, "invoice_date": "2026-03-02", "payment_terms_days": 15, **extra}
        return self.client.post("/api/invoices/", body, format="json")

    def _pay(self, invoice_id, amount, **extra):
        body = {"invoice": invoice_id, "amount": amount, "payment_date": "2026-03-10", "method": "upi", **extra}
        return self.client.post("/api/payments/", body, format="json")

    def test_invoice_copies_order_and_marks_it_invoiced(self):
        res = self._invoice()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["total"], "1180.00")
        self.assertEqual(res.data["due_date"], "2026-03-17")
        self.assertEqual(res.data["status"], "unpaid")
        self.assertTrue(res.data["invoice_no"].startswith("INV-2026-"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "invoiced")

    def test_only_confirmed_orders_can_be_invoiced(self):
        self.order.status = "draft"
        self.order.save()
        self.assertEqual(self._invoice().status_code, 400)

    def test_order_cannot_be_invoiced_twice(self):
        self._invoice()
        self.order.status = "confirmed"
        self.order.save()
        self.assertEqual(self._invoice().status_code, 400)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_invoiced_order_is_locked(self):
        self._invoice()
        self.client.force_authenticate(self.manager)
        res = self.client.patch(f"/api/sales-orders/{self.order.id}/", {"notes": "x"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_status_invoiced_cannot_be_set_by_hand(self):
        res = self.client.patch(f"/api/sales-orders/{self.order.id}/", {"status": "paid"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_partial_then_full_payment(self):
        inv = self._invoice().data["id"]
        self.assertEqual(self._pay(inv, "500").status_code, 201)
        data = self.client.get(f"/api/invoices/{inv}/").data
        self.assertEqual((data["status"], data["balance"]), ("partially_paid", "680.00"))
        self.assertEqual(self._pay(inv, "680").status_code, 201)
        data = self.client.get(f"/api/invoices/{inv}/").data
        self.assertEqual((data["status"], data["balance"]), ("paid", "0.00"))
        self.assertEqual(len(data["payments"]), 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")

    def test_overpayment_rejected(self):
        inv = self._invoice().data["id"]
        self.assertEqual(self._pay(inv, "1180.01").status_code, 400)
        self.assertEqual(self._pay(inv, "0").status_code, 400)

    def test_payment_before_invoice_date_rejected(self):
        inv = self._invoice().data["id"]
        self.assertEqual(self._pay(inv, "10", payment_date="2026-03-01").status_code, 400)

    def test_sales_user_cannot_record_payment_or_invoice(self):
        inv = self._invoice().data["id"]
        self.client.force_authenticate(self.sales)
        self.assertEqual(self._pay(inv, "10").status_code, 403)
        self.assertEqual(self.client.get(f"/api/invoices/{inv}/").status_code, 200)

    def test_deleting_payment_restores_balance(self):
        inv = self._invoice().data["id"]
        pay = self._pay(inv, "1180").data["id"]
        self.assertEqual(self.client.delete(f"/api/payments/{pay}/").status_code, 400)  # accountant can't
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.delete(f"/api/payments/{pay}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/invoices/{inv}/").data["status"], "unpaid")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "invoiced")

    def test_cancel_invoice(self):
        inv = self._invoice().data["id"]
        self._pay(inv, "100")
        self.assertEqual(self.client.post(f"/api/invoices/{inv}/cancel/").status_code, 400)
        Invoice.objects.get(id=inv).payments.all().delete()
        res = self.client.post(f"/api/invoices/{inv}/cancel/")
        self.assertEqual(res.data["status"], "cancelled")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self._pay(inv, "10").status_code, 400)

    def test_invoices_cannot_be_deleted(self):
        inv = self._invoice().data["id"]
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.delete(f"/api/invoices/{inv}/").status_code, 405)

    def test_pdf_download(self):
        inv = self._invoice(notes="Pay to A/c <123> & thanks").data["id"]
        res = self.client.get(f"/api/invoices/{inv}/pdf/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertIn("attachment", res["Content-Disposition"])
        self.assertTrue(res.content.startswith(b"%PDF"))

    def test_dashboard_receivables(self):
        inv = self._invoice().data["id"]
        self._pay(inv, "180")
        res = self.client.get("/api/reports/dashboard/")
        self.assertEqual(res.data["outstanding_receivables"], Decimal("1000.00"))
        self.assertEqual(res.data["overdue_invoices"], 1)  # due 2026-03-17, already past

    def test_report_rejects_bad_company(self):
        self.assertEqual(self.client.get("/api/reports/employee-sales/?company=abc").status_code, 400)


class PdfHelperTests(SimpleTestCase):
    def test_amount_in_words(self):
        self.assertEqual(amount_in_words(Decimal("1180")), "Rupees One Thousand One Hundred Eighty Only")
        self.assertEqual(
            amount_in_words(Decimal("1234567.50")),
            "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Fifty Paise Only",
        )
        self.assertEqual(amount_in_words(Decimal("0")), "Rupees Zero Only")
        self.assertEqual(amount_in_words(Decimal("25000000")), "Rupees Two Crore Fifty Lakh Only")

    def test_indian_number(self):
        self.assertEqual(indian_number(Decimal("1234567.5")), "12,34,567.50")
        self.assertEqual(indian_number(Decimal("999")), "999.00")
        self.assertEqual(indian_number(Decimal("100000")), "1,00,000.00")
