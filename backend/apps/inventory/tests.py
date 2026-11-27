from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.companies.models import Company
from apps.sales.models import Customer, Product, SalesOrder

from .models import StockLevel, StockMovement, Warehouse


class InventoryTests(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.client.force_authenticate(self.manager)
        self.company = Company.objects.create(name="A", code="A")
        self.other = Company.objects.create(name="B", code="B")
        self.wh = Warehouse.objects.create(company=self.company, code="MAIN", name="Main")
        self.wh2 = Warehouse.objects.create(company=self.company, code="DEPOT", name="Depot")
        self.foreign_wh = Warehouse.objects.create(company=self.other, code="MAIN", name="Other main")
        self.product = Product.objects.create(
            company=self.company, sku="V", name="Valve", unit_price=Decimal("100"),
            cost_price=Decimal("60"), reorder_level=Decimal("20"),
        )
        self.customer = Customer.objects.create(company=self.company, name="Cust")

    # helpers
    def receive(self, qty, wh=None):
        return self.client.post("/api/stock-movements/", {
            "movement_type": "receipt", "product": self.product.id, "warehouse": (wh or self.wh).id,
            "quantity": str(qty), "reference": "GRN-1",
        }, format="json")

    def on_hand(self, wh=None):
        level = StockLevel.objects.filter(product=self.product, warehouse=wh or self.wh).first()
        return level.quantity if level else Decimal("0")

    def order(self, qty, status="confirmed", wh=None):
        return self.client.post("/api/sales-orders/", {
            "company": self.company.id, "customer": self.customer.id, "order_date": "2026-03-01",
            "status": status, "warehouse": (wh or self.wh).id,
            "items": [{"product": self.product.id, "quantity": str(qty)}],
        }, format="json")

    # manual movements
    def test_receipt_and_issue_update_balance_and_ledger(self):
        res = self.receive(50)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["balance_after"], "50.00")
        res = self.client.post("/api/stock-movements/", {
            "movement_type": "issue", "product": self.product.id, "warehouse": self.wh.id, "quantity": "15",
        }, format="json")
        self.assertEqual(res.data["quantity"], "-15.00")
        self.assertEqual(self.on_hand(), Decimal("35"))
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_cannot_issue_more_than_on_hand(self):
        self.receive(5)
        res = self.client.post("/api/stock-movements/", {
            "movement_type": "issue", "product": self.product.id, "warehouse": self.wh.id, "quantity": "6",
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Not enough stock", str(res.data))
        self.assertEqual(self.on_hand(), Decimal("5"))

    def test_adjustment_needs_reason_and_can_be_negative(self):
        self.receive(10)
        body = {"movement_type": "adjustment", "product": self.product.id, "warehouse": self.wh.id, "quantity": "-3"}
        self.assertEqual(self.client.post("/api/stock-movements/", body, format="json").status_code, 400)
        body["note"] = "Stock count: 3 damaged"
        self.assertEqual(self.client.post("/api/stock-movements/", body, format="json").status_code, 201)
        self.assertEqual(self.on_hand(), Decimal("7"))

    def test_negative_receipt_rejected(self):
        self.assertEqual(self.receive(-5).status_code, 400)

    def test_other_company_warehouse_rejected(self):
        self.assertEqual(self.receive(5, wh=self.foreign_wh).status_code, 400)

    def test_inactive_warehouse_rejected(self):
        self.wh.is_active = False
        self.wh.save()
        self.assertEqual(self.receive(5).status_code, 400)

    def test_transfer(self):
        self.receive(20)
        res = self.client.post("/api/stock-movements/transfer/", {
            "product": self.product.id, "from_warehouse": self.wh.id, "to_warehouse": self.wh2.id, "quantity": "8",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((self.on_hand(), self.on_hand(self.wh2)), (Decimal("12"), Decimal("8")))
        res = self.client.post("/api/stock-movements/transfer/", {
            "product": self.product.id, "from_warehouse": self.wh.id, "to_warehouse": self.wh2.id, "quantity": "13",
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.on_hand(self.wh2), Decimal("8"))  # nothing half-done

    def test_ledger_cannot_be_edited_or_deleted(self):
        mv = self.receive(5).data["id"]
        self.assertEqual(self.client.delete(f"/api/stock-movements/{mv}/").status_code, 405)
        self.assertEqual(self.client.patch(f"/api/stock-movements/{mv}/", {"quantity": "50"}).status_code, 405)

    def test_sales_user_can_view_but_not_move_stock(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.receive(5).status_code, 403)
        self.assertEqual(self.client.get("/api/stock-levels/").status_code, 200)

    # sales orders
    def test_confirmed_order_takes_stock(self):
        self.receive(10)
        self.assertEqual(self.order(4).status_code, 201)
        self.assertEqual(self.on_hand(), Decimal("6"))

    def test_draft_order_takes_nothing_until_confirmed(self):
        self.receive(10)
        oid = self.order(4, status="draft").data["id"]
        self.assertEqual(self.on_hand(), Decimal("10"))
        res = self.client.patch(f"/api/sales-orders/{oid}/", {"status": "confirmed"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(self.on_hand(), Decimal("6"))

    def test_order_blocked_when_stock_short(self):
        self.receive(3)
        res = self.order(4)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(SalesOrder.objects.exists())  # whole order rolled back
        self.assertEqual(self.on_hand(), Decimal("3"))

    def test_cancel_returns_stock(self):
        self.receive(10)
        oid = self.order(4).data["id"]
        self.client.patch(f"/api/sales-orders/{oid}/", {"status": "cancelled"}, format="json")
        self.assertEqual(self.on_hand(), Decimal("10"))
        types = list(StockMovement.objects.filter(sales_order_id=oid).values_list("movement_type", flat=True))
        self.assertCountEqual(types, ["sale", "sale_return"])

    def test_editing_confirmed_order_quantity_rebalances(self):
        self.receive(10)
        oid = self.order(4).data["id"]
        res = self.client.patch(f"/api/sales-orders/{oid}/", {"items": [{"product": self.product.id, "quantity": "7"}]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(self.on_hand(), Decimal("3"))

    def test_editing_notes_does_not_touch_stock(self):
        self.receive(10)
        oid = self.order(4).data["id"]
        self.client.patch(f"/api/sales-orders/{oid}/", {"notes": "call before delivery"}, format="json")
        self.assertEqual(StockMovement.objects.filter(sales_order_id=oid).count(), 1)

    def test_moving_order_to_other_warehouse(self):
        self.receive(10)
        self.receive(10, wh=self.wh2)
        oid = self.order(4).data["id"]
        self.client.patch(f"/api/sales-orders/{oid}/", {"warehouse": self.wh2.id}, format="json")
        self.assertEqual((self.on_hand(), self.on_hand(self.wh2)), (Decimal("10"), Decimal("6")))

    def test_order_without_warehouse_ignores_stock(self):
        res = self.client.post("/api/sales-orders/", {
            "company": self.company.id, "customer": self.customer.id, "order_date": "2026-03-01", "status": "confirmed",
            "items": [{"product": self.product.id, "quantity": "4"}],
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_order_with_other_company_warehouse_rejected(self):
        self.assertEqual(self.order(1, wh=self.foreign_wh).status_code, 400)

    def test_invoice_cancel_returns_stock(self):
        self.receive(10)
        oid = self.order(4).data["id"]
        inv = self.client.post("/api/invoices/", {"sales_order": oid}, format="json").data["id"]
        self.assertEqual(self.on_hand(), Decimal("6"))
        self.client.post(f"/api/invoices/{inv}/cancel/")
        self.assertEqual(self.on_hand(), Decimal("10"))

    # views
    def test_low_stock_uses_total_across_warehouses(self):
        self.receive(15)            # main: 15
        self.receive(10, wh=self.wh2)  # depot: 10 -> total 25, reorder level 20
        res = self.client.get("/api/stock-levels/?low_stock=true")
        self.assertEqual(res.data["count"], 0)  # neither warehouse alone has 20, but the total does
        rows = self.client.get("/api/stock-levels/").data["results"]
        self.assertEqual({r["product_total"] for r in rows}, {"25.00"})
        self.assertFalse(any(r["is_low_stock"] for r in rows))

    def test_low_stock_filter_product_stock_and_dashboard(self):
        self.receive(25)
        self.assertEqual(self.client.get("/api/stock-levels/?low_stock=true").data["count"], 0)
        self.order(6)  # 19 left, reorder level 20
        self.assertEqual(self.client.get("/api/stock-levels/?low_stock=true").data["count"], 1)
        product = self.client.get(f"/api/products/{self.product.id}/").data
        self.assertEqual((product["stock_on_hand"], product["is_low_stock"]), ("19.00", True))
        dash = self.client.get("/api/reports/dashboard/").data
        self.assertEqual(dash["low_stock_products"], 1)
        self.assertEqual(dash["stock_value"], Decimal("1140.00"))  # 19 x 60
