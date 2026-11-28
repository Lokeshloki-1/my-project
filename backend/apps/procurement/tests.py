from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.companies.models import Company
from apps.development.models import BOMItem, TechPack
from apps.merchandising.models import CostSheet, OrderConfirmation, OrderConfirmationLine, Quotation
from apps.sales.models import Customer

from .models import PurchaseOrder, RFQ, Supplier


class ProcurementTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM", address="SIDCO, Tiruppur")
        customer = Customer.objects.create(company=self.company, name="Nordic")
        self.buyer = Buyer.objects.create(company=self.company, legal_name="Nordic", country="Sweden",
                                          status=Buyer.Status.APPROVED, customer=customer)
        # Two styles share the same main fabric; one label is only on the tee.
        self._tech_pack("NT-101", [("fabric", "180 GSM jersey", "Navy", "kg", "0.20"), ("label", "Main label", "", "pc", "1"),
                                   ("trim", "Neck tape", "", "m", None)])
        self._tech_pack("NT-205", [("fabric", "180 GSM jersey", "Navy", "kg", "0.40")])
        self.order = self._order([("NT-101", 1000), ("NT-205", 500), ("NT-999", 100)])
        self.s1 = Supplier.objects.create(company=self.company, name="Knit Fabrics", payment_terms="30 days")
        self.s2 = Supplier.objects.create(company=self.company, name="Fabric House")
        self.client.force_authenticate(self.sales)

    def _tech_pack(self, style, bom):
        tp = TechPack.objects.create(company=self.company, buyer=self.buyer, style_no=style, style_name=style,
                                     sizes=["M"], status=TechPack.Status.RELEASED, production_approved=True)
        for cat, desc, colour, unit, cons in bom:
            BOMItem.objects.create(tech_pack=tp, category=cat, description=desc, colour=colour, unit=unit,
                                   consumption=Decimal(cons) if cons else None)

    def _order(self, lines):
        q = Quotation.objects.create(company=self.company, buyer=self.buyer, quote_date=date(2026, 11, 1),
                                     valid_until=date(2026, 12, 1), status="accepted")
        oc = OrderConfirmation.objects.create(company=self.company, buyer=self.buyer, quotation=q, currency="USD",
                                              incoterm="FOB", payment_terms="lc_sight", buyer_po_no="PO1",
                                              ship_date=date(2027, 3, 1), status="confirmed")
        for style, qty in lines:
            sheet = CostSheet.objects.create(company=self.company, buyer=self.buyer, style_no=style, style_name=style)
            OrderConfirmationLine.objects.create(order=oc, cost_sheet=sheet, style_no=style, description=style,
                                                 quantity=qty, unit_price=Decimal("3"))
        return oc

    def as_user(self, user):
        self.client.force_authenticate(user)

    def requirement(self, approve=True):
        res = self.client.post("/api/material-requirements/generate/", {"order": self.order.id, "wastage_pct": "5"})
        self.assertEqual(res.status_code, 201, res.data)
        if approve:
            self.as_user(self.manager)
            res = self.client.post(f"/api/material-requirements/{res.data['id']}/approve/")
            self.assertEqual(res.status_code, 200, res.data)
            self.as_user(self.sales)
        return res.data

    def rfq(self, mr, suppliers=None, send=True):
        lines = [{"requirement_line": line["id"], "category": line["category"], "description": line["description"],
                  "colour": line["colour"], "unit": line["unit"], "quantity": line["required_qty"]} for line in mr["lines"]]
        res = self.client.post("/api/rfqs/", {
            "company": self.company.id, "requirement": mr["id"], "title": "Fabric", "reply_by": "2026-12-05",
            "required_by": "2027-01-10", "lines": lines, "suppliers": suppliers if suppliers is not None else [self.s1.id, self.s2.id],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        if send:
            res = self.client.post(f"/api/rfqs/{res.data['id']}/send/")
            self.assertEqual(res.status_code, 200, res.data)
        return res.data

    def quote(self, rfq, supplier, prices):
        return self.client.post(f"/api/rfqs/{rfq['id']}/quotes/", {
            "supplier": supplier.id, "currency": "inr", "payment_terms": "45 days",
            "lines": [{"rfq_line": line["id"], "unit_price": p} for line, p in zip(rfq["lines"], prices)],
        }, format="json")

    # ---- requirements
    def test_generate_merges_materials_and_applies_wastage(self):
        mr = self.requirement(approve=False)
        lines = {line["description"]: line for line in mr["lines"]}
        fabric = lines["180 GSM jersey"]
        self.assertEqual(fabric["net_qty"], "400.00")          # 1000×0.20 + 500×0.40
        self.assertEqual(fabric["required_qty"], "420.00")     # +5%
        self.assertEqual(fabric["styles"], "NT-101, NT-205")
        self.assertEqual(lines["Main label"]["required_qty"], "1050.00")
        self.assertNotIn("Neck tape", lines)
        warnings = " ".join(mr["warnings"])
        self.assertIn("NT-999: no released tech pack", warnings)
        self.assertIn("Neck tape", warnings)
        self.assertEqual(mr["needed_by"], "2027-01-15")        # ship date − 45 days

    def test_generate_is_idempotent_and_needs_confirmed_order(self):
        first = self.requirement(approve=False)
        again = self.client.post("/api/material-requirements/generate/", {"order": self.order.id})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["id"], first["id"])
        draft = self._order([("NT-101", 10)])
        OrderConfirmation.objects.filter(pk=draft.pk).update(status="draft")
        self.assertEqual(self.client.post("/api/material-requirements/generate/", {"order": draft.id}).status_code, 409)

    def test_only_manager_approves_and_approved_is_locked(self):
        mr = self.requirement(approve=False)
        self.assertEqual(self.client.post(f"/api/material-requirements/{mr['id']}/approve/").status_code, 403)
        self.as_user(self.manager)
        self.client.post(f"/api/material-requirements/{mr['id']}/approve/")
        self.as_user(self.sales)
        res = self.client.patch(f"/api/material-requirements/{mr['id']}/", {"notes": "x"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_edit_lines_by_hand_in_draft(self):
        mr = self.requirement(approve=False)
        lines = [{**line} for line in mr["lines"]]
        lines[0]["required_qty"] = "450"
        lines.append({"category": "trim", "description": "Neck tape", "unit": "m", "required_qty": "600"})
        res = self.client.patch(f"/api/material-requirements/{mr['id']}/", {"lines": lines}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data["lines"]), 3)
        self.assertEqual(res.data["lines"][0]["required_qty"], "450.00")
        self.assertEqual(res.data["lines"][0]["id"], mr["lines"][0]["id"])   # same row kept

    # ---- RFQs
    def test_rfq_needs_approved_requirement_and_suppliers(self):
        mr = self.requirement(approve=False)
        res = self.client.post("/api/rfqs/", {"company": self.company.id, "requirement": mr["id"], "title": "x",
                                              "reply_by": "2026-12-05", "lines": [{"description": "x", "quantity": 1}]}, format="json")
        self.assertEqual(res.status_code, 400)
        mr = self.client.get(f"/api/material-requirements/{mr['id']}/").data
        self.as_user(self.manager)
        self.client.post(f"/api/material-requirements/{mr['id']}/approve/")
        mr = self.client.get(f"/api/material-requirements/{mr['id']}/").data
        rfq = self.rfq(mr, suppliers=[], send=False)
        res = self.client.post(f"/api/rfqs/{rfq['id']}/send/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("suppliers", res.data)

    def test_quotes_compare_and_award_creates_po(self):
        mr = self.requirement()
        rfq = self.rfq(mr)
        self.assertEqual(self.quote(rfq, self.s1, ["520", "1.20"]).status_code, 200)
        res = self.quote(rfq, self.s2, ["500", "1.50"])
        self.assertEqual(res.status_code, 200)
        cmp = res.data["comparison"]
        fabric = cmp["lines"][0]["offers"]
        best = {o["supplier"]: o["best"] for o in fabric}
        self.assertTrue(best[self.s2.id])
        self.assertFalse(best[self.s1.id])
        totals = {s["supplier"]: (s["total"], s["lowest"]) for s in cmp["suppliers"]}
        self.assertEqual(totals[self.s1.id], (Decimal("219660.00"), False))   # 420×520 + 1050×1.20
        self.assertEqual(totals[self.s2.id], (Decimal("211575.00"), True))    # 420×500 + 1050×1.50, cheapest
        res = self.client.post(f"/api/rfqs/{rfq['id']}/award/", {"supplier": self.s1.id})
        self.assertEqual(res.status_code, 201, res.data)
        po = res.data
        self.assertEqual(po["status"], "draft")
        self.assertEqual(po["supplier"], self.s1.id)
        self.assertEqual(po["total"], "219660.00")
        self.assertEqual(po["currency"], "INR")
        self.assertEqual(po["payment_terms"], "45 days")
        self.assertEqual(po["delivery_address"], "SIDCO, Tiruppur")
        self.assertEqual(RFQ.objects.get(pk=rfq["id"]).status, "awarded")
        again = self.client.post(f"/api/rfqs/{rfq['id']}/award/", {"supplier": self.s2.id})
        self.assertEqual(again.data["id"], po["id"])

    def test_lowest_total_flag(self):
        mr = self.requirement()
        rfq = self.rfq(mr)
        self.quote(rfq, self.s1, ["520", "1.20"])   # 218400 + 1260 = 219660
        res = self.quote(rfq, self.s2, ["500", "1.50"])  # 210000 + 1575 = 211575
        lowest = [s["supplier"] for s in res.data["comparison"]["suppliers"] if s["lowest"]]
        self.assertEqual(lowest, [self.s2.id])

    def test_partial_quote_cannot_be_awarded_and_uninvited_rejected(self):
        mr = self.requirement()
        rfq = self.rfq(mr, suppliers=[self.s1.id])
        res = self.client.post(f"/api/rfqs/{rfq['id']}/quotes/", {
            "supplier": self.s1.id, "lines": [{"rfq_line": rfq["lines"][0]["id"], "unit_price": "500"}]}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["comparison"]["suppliers"][0]["complete"])
        self.assertEqual(self.client.post(f"/api/rfqs/{rfq['id']}/award/", {"supplier": self.s1.id}).status_code, 400)
        self.assertEqual(self.quote(rfq, self.s2, ["1", "1"]).status_code, 400)

    def test_quote_only_while_sent(self):
        mr = self.requirement()
        rfq = self.rfq(mr, send=False)
        self.assertEqual(self.quote(rfq, self.s1, ["1", "1"]).status_code, 409)

    # ---- purchase orders
    def test_direct_po_and_ordered_quantities(self):
        mr = self.requirement()
        fabric = mr["lines"][0]
        res = self.client.post("/api/purchase-orders/", {
            "supplier": self.s1.id, "requirement": mr["id"], "order_date": "2026-11-27", "delivery_date": "2026-12-20",
            "lines": [{"requirement_line": fabric["id"], "category": "fabric", "description": fabric["description"],
                       "unit": "kg", "quantity": "300", "unit_price": "510"}],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        po = res.data
        self.assertEqual(po["total"], "153000.00")
        self.assertEqual(po["payment_terms"], "30 days")
        self.assertEqual(po["lines"][0]["ordered_total"], Decimal("300.00"))
        line = self.client.get(f"/api/material-requirements/{mr['id']}/").data["lines"][0]
        self.assertEqual(line["ordered_qty"], Decimal("300.00"))
        self.assertEqual(line["open_qty"], Decimal("120.00"))
        self.assertEqual(line["po_nos"], [po["po_no"]])

    def test_po_approve_send_cancel_flow(self):
        mr = self.requirement()
        fabric = mr["lines"][0]
        po = self.client.post("/api/purchase-orders/", {
            "supplier": self.s1.id, "order_date": "2026-11-27",
            "lines": [{"requirement_line": fabric["id"], "description": "Jersey", "unit": "kg", "quantity": "500", "unit_price": "500"}],
        }, format="json").data
        self.assertEqual(self.client.post(f"/api/purchase-orders/{po['id']}/approve/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/purchase-orders/{po['id']}/send/").status_code, 409)
        self.as_user(self.manager)
        res = self.client.post(f"/api/purchase-orders/{po['id']}/approve/")
        self.assertEqual(res.data["status"], "approved")
        self.assertIn("Over the requirement", res.data["history"][-1]["note"])   # 500 > 420
        self.as_user(self.sales)
        self.assertEqual(self.client.patch(f"/api/purchase-orders/{po['id']}/", {"notes": "x"}, format="json").status_code, 409)
        res = self.client.post(f"/api/purchase-orders/{po['id']}/send/")
        self.assertEqual(res.data["status"], "sent")
        self.assertEqual(self.client.post(f"/api/purchase-orders/{po['id']}/cancel/", {"reason": "x"}).status_code, 403)
        self.as_user(self.manager)
        res = self.client.post(f"/api/purchase-orders/{po['id']}/cancel/", {"reason": "Supplier can't deliver"})
        self.assertEqual(res.data["status"], "cancelled")
        line = self.client.get(f"/api/material-requirements/{mr['id']}/").data["lines"][0]
        self.assertEqual(line["ordered_qty"], Decimal("0"))   # cancelled PO frees the quantity

    def test_po_from_unapproved_requirement_rejected(self):
        mr = self.requirement(approve=False)
        res = self.client.post("/api/purchase-orders/", {
            "supplier": self.s1.id, "order_date": "2026-11-27",
            "lines": [{"requirement_line": mr["lines"][0]["id"], "description": "x", "quantity": "1", "unit_price": "1"}],
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_inactive_supplier_cannot_be_approved_and_used_supplier_not_deleted(self):
        po = self.client.post("/api/purchase-orders/", {
            "supplier": self.s2.id, "order_date": "2026-11-27",
            "lines": [{"description": "Buttons", "category": "trim", "quantity": "100", "unit_price": "0.5"}],
        }, format="json").data
        Supplier.objects.filter(pk=self.s2.id).update(is_active=False)
        self.as_user(self.manager)
        self.assertEqual(self.client.post(f"/api/purchase-orders/{po['id']}/approve/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/suppliers/{self.s2.id}/").status_code, 409)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
