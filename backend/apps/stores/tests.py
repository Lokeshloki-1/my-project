from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.companies.models import Company
from apps.inventory.models import Warehouse
from apps.merchandising.models import OrderConfirmation, Quotation
from apps.procurement.models import MaterialRequirement, PurchaseOrder, PurchaseOrderLine, RequirementLine, Supplier
from apps.sales.models import Customer

from .models import MaterialMovement, MaterialStock


class StoresTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        self.wh = Warehouse.objects.create(company=self.company, code="RMS", name="Raw Material Store")
        self.wh2 = Warehouse.objects.create(company=self.company, code="UNIT2", name="Unit 2 Store")
        customer = Customer.objects.create(company=self.company, name="Nordic")
        self.buyer = Buyer.objects.create(company=self.company, legal_name="Nordic", country="SE",
                                          status=Buyer.Status.APPROVED, customer=customer)
        q = Quotation.objects.create(company=self.company, buyer=self.buyer, quote_date=date(2026, 11, 1),
                                     valid_until=date(2026, 12, 1), status="accepted")
        self.order = OrderConfirmation.objects.create(company=self.company, buyer=self.buyer, quotation=q, currency="USD",
                                                      incoterm="FOB", payment_terms="lc_sight", buyer_po_no="PO1",
                                                      ship_date=date(2027, 3, 1), status="confirmed")
        self.mr = MaterialRequirement.objects.create(company=self.company, order=self.order, title="MR", status="approved")
        self.req_fabric = RequirementLine.objects.create(requirement=self.mr, category="fabric", description="180 GSM jersey",
                                                         colour="Navy", unit="kg", required_qty=Decimal("400"))
        self.supplier = Supplier.objects.create(company=self.company, name="Knit Fabrics")
        self.po = PurchaseOrder.objects.create(company=self.company, supplier=self.supplier, requirement=self.mr,
                                               order_date=date(2026, 11, 20), status="sent")
        self.pl_fabric = PurchaseOrderLine.objects.create(order=self.po, requirement_line=self.req_fabric, category="fabric",
                                                          description="180 GSM jersey", colour="Navy", unit="kg",
                                                          quantity=Decimal("400"), unit_price=Decimal("500"))
        self.pl_label = PurchaseOrderLine.objects.create(order=self.po, category="label", description="Main label", unit="pc",
                                                         quantity=Decimal("1000"), unit_price=Decimal("2"))
        self.client.force_authenticate(self.sales)

    def as_user(self, user):
        self.client.force_authenticate(user)

    def grn(self, lines, submit=True, warehouse=None):
        res = self.client.post("/api/goods-receipts/", {
            "purchase_order": self.po.id, "warehouse": (warehouse or self.wh).id, "received_on": "2026-12-01",
            "challan_no": "DC-77", "lines": [{"po_line": pl.id, "received_qty": q, "lot_no": "L1"} for pl, q in lines],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        if submit:
            res = self.client.post(f"/api/goods-receipts/{res.data['id']}/submit/")
            self.assertEqual(res.status_code, 200, res.data)
        return res.data

    def inspect(self, grn, results, notes=""):
        return self.client.post(f"/api/goods-receipts/{grn['id']}/inspect/", {"results": results, "notes": notes}, format="json")

    def stocked(self, qty="400"):
        grn = self.grn([(self.pl_fabric, qty)])
        res = self.inspect(grn, [{"line": grn["lines"][0]["id"], "accepted_qty": qty, "rejected_qty": "0"}])
        self.assertEqual(res.status_code, 200, res.data)
        return res.data["lines"][0]["material"]

    # ---- goods receipt
    def test_receivable_lines(self):
        self.grn([(self.pl_fabric, "150")])
        res = self.client.get(f"/api/goods-receipts/receivable/?purchase_order={self.po.id}")
        fabric = res.data["lines"][0]
        self.assertEqual(fabric["received_qty"], Decimal("150"))
        self.assertEqual(fabric["open_qty"], Decimal("250"))

    def test_grn_needs_sent_po(self):
        PurchaseOrder.objects.filter(pk=self.po.pk).update(status="approved")
        res = self.client.post("/api/goods-receipts/", {"purchase_order": self.po.id, "warehouse": self.wh.id,
                                                        "received_on": "2026-12-01", "lines": [{"po_line": self.pl_fabric.id, "received_qty": "1"}]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_over_receipt_tolerance(self):
        grn = self.grn([(self.pl_fabric, "440")])   # 400 + 10%
        self.assertEqual(grn["status"], "received")
        res = self.client.post("/api/goods-receipts/", {"purchase_order": self.po.id, "warehouse": self.wh.id,
                                                        "received_on": "2026-12-02", "lines": [{"po_line": self.pl_fabric.id, "received_qty": "1"}]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_draft_does_not_count_and_submit_rechecks(self):
        a = self.grn([(self.pl_fabric, "300")], submit=False)
        b = self.grn([(self.pl_fabric, "300")], submit=False)   # both fine as drafts
        self.assertEqual(self.client.post(f"/api/goods-receipts/{a['id']}/submit/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/goods-receipts/{b['id']}/submit/").status_code, 400)  # 600 > 440

    def test_line_from_another_po_rejected(self):
        other = PurchaseOrder.objects.create(company=self.company, supplier=self.supplier, order_date=date(2026, 11, 20), status="sent")
        ol = PurchaseOrderLine.objects.create(order=other, description="X", quantity=1, unit_price=1)
        res = self.client.post("/api/goods-receipts/", {"purchase_order": self.po.id, "warehouse": self.wh.id,
                                                        "received_on": "2026-12-01", "lines": [{"po_line": ol.id, "received_qty": "1"}]}, format="json")
        self.assertEqual(res.status_code, 400)

    # ---- inspection
    def test_no_stock_until_inspected_then_only_accepted(self):
        grn = self.grn([(self.pl_fabric, "400"), (self.pl_label, "1000")])
        self.assertFalse(MaterialStock.objects.exists())
        fabric, label = grn["lines"]
        res = self.inspect(grn, [
            {"line": fabric["id"], "accepted_qty": "380", "rejected_qty": "20", "remarks": "Shade variation in 2 rolls"},
            {"line": label["id"], "accepted_qty": "1000", "rejected_qty": "0"},
        ], notes="4-point check on 10% of rolls")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "inspected")
        self.assertEqual(res.data["lines"][0]["result"], "partial")
        self.assertEqual(res.data["totals"], {"received": Decimal("1400.00"), "accepted": Decimal("1380.00"), "rejected": Decimal("20.00")})
        stock = MaterialStock.objects.get(material__description="180 GSM jersey")
        self.assertEqual(stock.on_hand, Decimal("380"))
        self.assertEqual(stock.value, Decimal("190000.00"))      # 380 × 500
        mv = MaterialMovement.objects.get(material=stock.material)
        self.assertEqual(mv.reference, res.data["grn_no"])
        po = self.client.get(f"/api/purchase-orders/{self.po.id}/").data
        self.assertEqual(po["lines"][0]["received_qty"], Decimal("400"))
        self.assertEqual(po["lines"][0]["accepted_qty"], Decimal("380"))

    def test_inspection_must_add_up_and_explain_rejects(self):
        grn = self.grn([(self.pl_fabric, "400")])
        lid = grn["lines"][0]["id"]
        self.assertEqual(self.inspect(grn, [{"line": lid, "accepted_qty": "390", "rejected_qty": "0"}]).status_code, 400)
        self.assertEqual(self.inspect(grn, [{"line": lid, "accepted_qty": "390", "rejected_qty": "10"}]).status_code, 400)
        self.assertEqual(self.inspect(grn, [{"line": lid, "accepted_qty": "390", "rejected_qty": "10", "remarks": "Holes"}]).status_code, 200)
        self.assertEqual(self.inspect(grn, [{"line": lid, "accepted_qty": "400", "rejected_qty": "0"}]).status_code, 409)

    def test_same_material_merges_across_receipts(self):
        self.stocked("200")
        self.stocked("150")
        stock = MaterialStock.objects.get()
        self.assertEqual(stock.on_hand, Decimal("350"))

    # ---- allocation
    def test_allocate_release_issue(self):
        material = self.stocked("400")
        res = self.client.post("/api/material-allocations/", {"order": self.order.id, "material": material, "warehouse": self.wh.id,
                                                              "requirement_line": self.req_fabric.id, "quantity": "300"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        alloc = res.data
        stock = MaterialStock.objects.get()
        self.assertEqual((stock.on_hand, stock.allocated, stock.available), (Decimal("400"), Decimal("300"), Decimal("100")))
        over = self.client.post("/api/material-allocations/", {"order": self.order.id, "material": material,
                                                               "warehouse": self.wh.id, "quantity": "150"}, format="json")
        self.assertEqual(over.status_code, 400)
        res = self.client.post(f"/api/material-allocations/{alloc['id']}/issue/", {"quantity": "200"})
        self.assertEqual(res.data["issued_qty"], "200.00")
        self.assertEqual(res.data["status"], "active")
        res = self.client.post(f"/api/material-allocations/{alloc['id']}/release/")
        self.assertEqual(res.data["status"], "issued")
        self.assertEqual(res.data["released_qty"], "100.00")
        stock.refresh_from_db()
        self.assertEqual((stock.on_hand, stock.allocated), (Decimal("200"), Decimal("0")))
        self.assertEqual(stock.value, Decimal("100000.00"))
        self.assertEqual(self.client.post(f"/api/material-allocations/{alloc['id']}/issue/").status_code, 409)

    def test_allocation_needs_confirmed_order(self):
        material = self.stocked()
        OrderConfirmation.objects.filter(pk=self.order.pk).update(status="cancelled")
        res = self.client.post("/api/material-allocations/", {"order": self.order.id, "material": material,
                                                              "warehouse": self.wh.id, "quantity": "10"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_plan_and_auto_allocate(self):
        self.stocked("250")
        grn = self.grn([(self.pl_fabric, "100")], warehouse=self.wh2)
        self.inspect(grn, [{"line": grn["lines"][0]["id"], "accepted_qty": "100", "rejected_qty": "0"}])
        plan = self.client.get(f"/api/material-allocations/plan/?requirement={self.mr.id}").data
        row = plan["lines"][0]
        self.assertEqual(row["still_needed"], Decimal("400"))
        self.assertEqual(len(row["stock"]), 2)
        res = self.client.post("/api/material-allocations/auto/", {"requirement": self.mr.id, "warehouse": self.wh2.id})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual([a["warehouse"] for a in res.data], [self.wh2.id, self.wh.id])   # preferred first
        self.assertEqual(sum(Decimal(a["quantity"]) for a in res.data), Decimal("350"))
        row = self.client.get(f"/api/material-allocations/plan/?requirement={self.mr.id}").data["lines"][0]
        self.assertEqual(row["allocated_qty"], Decimal("350"))
        self.assertEqual(row["still_needed"], Decimal("50"))
        self.assertEqual(self.client.post("/api/material-allocations/auto/", {"requirement": self.mr.id}).status_code, 400)

    # ---- adjustments
    def test_adjust_is_manager_only_and_respects_allocation(self):
        material = self.stocked("400")
        body = {"material": material, "warehouse": self.wh.id, "new_quantity": "390", "reason": "Stock count"}
        self.assertEqual(self.client.post("/api/material-stock/adjust/", body).status_code, 403)
        self.client.post("/api/material-allocations/", {"order": self.order.id, "material": material,
                                                        "warehouse": self.wh.id, "quantity": "395"}, format="json")
        self.as_user(self.manager)
        self.assertEqual(self.client.post("/api/material-stock/adjust/", body).status_code, 400)   # below allocated
        body["new_quantity"] = "398"
        res = self.client.post("/api/material-stock/adjust/", body)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["quantity"], "-2.00")
        self.assertEqual(MaterialStock.objects.get().on_hand, Decimal("398"))

    def test_movements_are_read_only(self):
        self.stocked()
        mv = MaterialMovement.objects.first()
        self.assertEqual(self.client.delete(f"/api/material-movements/{mv.id}/").status_code, 405)
        self.assertEqual(self.client.post("/api/material-movements/", {}).status_code, 405)
