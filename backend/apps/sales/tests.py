from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.companies.models import Company
from apps.employees.models import Employee
from apps.sales.models import Customer, Product, SalesOrder


class SalesOrderApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("sam", password="pass12345!", role=User.Role.SALES)
        self.client.force_authenticate(self.user)
        self.company = Company.objects.create(name="A", code="A")
        self.other = Company.objects.create(name="B", code="B")
        self.customer = Customer.objects.create(company=self.company, name="Cust")
        self.product = Product.objects.create(
            company=self.company, sku="X", name="X", unit_price=Decimal("100.00"), tax_rate=Decimal("18")
        )
        self.emp = Employee.objects.create(
            company=self.company, employee_code="E1", first_name="Asha",
            date_joined=date(2025, 1, 1), monthly_sales_target=Decimal("1000"),
        )

    def _order(self, **extra):
        body = {
            "company": self.company.id, "customer": self.customer.id, "salesperson": self.emp.id,
            "order_date": "2026-03-10", "status": "confirmed",
            "items": [{"product": self.product.id, "quantity": "3"}],
        }
        body.update(extra)
        return self.client.post("/api/sales-orders/", body, format="json")

    def test_totals_are_calculated_on_server(self):
        res = self._order()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["subtotal"], "300.00")
        self.assertEqual(res.data["tax_amount"], "54.00")
        self.assertEqual(res.data["total"], "354.00")
        self.assertTrue(res.data["order_no"].startswith("SO-2026-"))

    def test_client_cannot_override_total(self):
        res = self._order(total="1.00")
        self.assertEqual(res.data["total"], "354.00")

    def test_customer_from_other_company_rejected(self):
        foreign = Customer.objects.create(company=self.other, name="Foreign")
        res = self._order(customer=foreign.id)
        self.assertEqual(res.status_code, 400)

    def test_empty_items_rejected(self):
        self.assertEqual(self._order(items=[]).status_code, 400)

    def test_confirmed_order_cannot_be_deleted(self):
        order_id = self._order().data["id"]
        self.assertEqual(self.client.delete(f"/api/sales-orders/{order_id}/").status_code, 400)
        self.assertTrue(SalesOrder.objects.filter(id=order_id).exists())

    def test_sales_user_cannot_create_company(self):
        res = self.client.post("/api/companies/", {"name": "C", "code": "C"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/sales-orders/").status_code, 401)

    def test_monthly_and_employee_reports(self):
        self._order()
        self._order(status="draft")  # drafts are not counted
        res = self.client.get("/api/reports/monthly-sales/?year=2026")
        march = res.data["months"][2]
        self.assertEqual(march["total"], Decimal("354.00"))
        self.assertEqual(march["orders"], 1)

        res = self.client.get("/api/reports/employee-sales/?year=2026&month=3")
        row = res.data["employees"][0]
        self.assertEqual(row["sales"], Decimal("354.00"))
        self.assertEqual(row["achievement_percent"], 35.4)

    def test_bad_report_params_rejected(self):
        self.assertEqual(self.client.get("/api/reports/employee-sales/?month=13").status_code, 400)
