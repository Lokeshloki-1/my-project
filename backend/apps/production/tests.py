from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.companies.models import Company
from apps.development.models import TechPack
from apps.merchandising.models import CostSheet, OrderConfirmation, OrderConfirmationLine, Quotation
from apps.sales.models import Customer

from .models import ProductionLine, ProductionOrder
from .services import add_working_days


class ProductionTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        customer = Customer.objects.create(company=self.company, name="Nordic")
        self.buyer = Buyer.objects.create(company=self.company, legal_name="Nordic", country="SE",
                                          status=Buyer.Status.APPROVED, customer=customer)
        q = Quotation.objects.create(company=self.company, buyer=self.buyer, quote_date=date(2026, 11, 1),
                                     valid_until=date(2026, 12, 1), status="accepted")
        self.order = OrderConfirmation.objects.create(company=self.company, buyer=self.buyer, quotation=q, currency="USD",
                                                      incoterm="FOB", payment_terms="lc_sight", buyer_po_no="PO1",
                                                      ship_date=date(2027, 3, 1), status="confirmed")
        sheet = CostSheet.objects.create(company=self.company, buyer=self.buyer, style_no="NT-101", style_name="Tee")
        self.oline = OrderConfirmationLine.objects.create(order=self.order, cost_sheet=sheet, style_no="NT-101",
                                                          description="Tee", quantity=1000, unit_price=Decimal("3"))
        self.tp = TechPack.objects.create(company=self.company, buyer=self.buyer, style_no="NT-101", style_name="Tee",
                                          sizes=["4Y", "6Y", "8Y"], status="released", production_approved=True)
        # 30 operators × 480 min × 60% ÷ 12 SMV = 720 pcs/day
        self.line = ProductionLine.objects.create(company=self.company, code="L1", name="Line 1", operators=30,
                                                  working_minutes=480, efficiency_pct=Decimal("60"))
        self.client.force_authenticate(self.sales)
        self.today = timezone.localdate()

    def as_user(self, user):
        self.client.force_authenticate(user)

    def plan(self, quantity=1000, sizes=None, **extra):
        body = {"order": self.order.id, "order_line": self.oline.id, "quantity": quantity,
                "sizes": sizes or {"4Y": 300, "6Y": 400, "8Y": 300}, "line": self.line.id, "smv": "12",
                "planned_start": str(self.today), **extra}
        return self.client.post("/api/production-orders/", body, format="json")

    def wo(self, **extra):
        res = self.plan(**extra)
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def entry(self, wo, **data):
        return self.client.post(f"/api/production-orders/{wo['id']}/entries/", {"date": str(self.today), **data}, format="json")

    # ---- planning
    def test_capacity_and_suggested_end(self):
        wo = self.wo()
        self.assertEqual(wo["capacity"]["daily_target"], 720)
        self.assertEqual(wo["capacity"]["working_days"], 2)
        self.assertEqual(wo["planned_end"], str(add_working_days(self.today, 2)))
        self.assertEqual(wo["tech_pack"], self.tp.id)    # found automatically
        self.assertTrue(wo["wo_no"].startswith("WO-"))

    def test_working_days_skip_sunday(self):
        saturday = date(2026, 11, 28)
        self.assertEqual(add_working_days(saturday, 2), date(2026, 11, 30))

    def test_sizes_must_add_up_and_match_tech_pack(self):
        self.assertEqual(self.plan(sizes={"4Y": 300, "6Y": 300}).status_code, 400)
        res = self.plan(sizes={"4Y": 500, "XL": 500})
        self.assertEqual(res.status_code, 400)
        self.assertIn("XL", str(res.data))

    def test_cannot_overplan_order(self):
        self.wo(quantity=700, sizes={"4Y": 200, "6Y": 300, "8Y": 200})
        self.assertEqual(self.plan(quantity=400, sizes={"4Y": 100, "6Y": 200, "8Y": 100}).status_code, 400)  # 1100 > 1050
        self.assertEqual(self.plan(quantity=350, sizes={"4Y": 100, "6Y": 150, "8Y": 100}).status_code, 201)

    def test_order_must_be_confirmed(self):
        OrderConfirmation.objects.filter(pk=self.order.pk).update(status="draft")
        self.assertEqual(self.plan().status_code, 400)

    def test_warnings_for_late_plan_and_line_clash(self):
        self.wo(quantity=500, sizes={"4Y": 100, "6Y": 300, "8Y": 100})
        wo = self.wo(quantity=500, sizes={"4Y": 100, "6Y": 300, "8Y": 100}, planned_end=str(date(2027, 3, 5)))
        text = " ".join(wo["warnings"])
        self.assertIn("after the shipment date", text)
        self.assertIn("also booked", text)

    def test_order_lines_for_planning(self):
        self.wo(quantity=600, sizes={"4Y": 200, "6Y": 200, "8Y": 200})
        res = self.client.get(f"/api/production-orders/order-lines/?order={self.order.id}")
        row = res.data["lines"][0]
        self.assertEqual((row["quantity"], row["planned"]), (1000, 600))
        self.assertEqual(row["sizes"], ["4Y", "6Y", "8Y"])

    # ---- output
    def test_stages_cannot_overtake(self):
        wo = self.wo()
        self.assertEqual(self.entry(wo, stage="sewing", quantity=10).status_code, 400)        # nothing cut yet
        res = self.entry(wo, stage="cutting", sizes={"4Y": 300, "6Y": 200})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status"], "in_progress")
        self.assertEqual(res.data["progress"]["cut"], 500)
        self.assertEqual(self.entry(wo, stage="sewing", quantity=480, rejected=30).status_code, 400)   # 510 > 500
        res = self.entry(wo, stage="sewing", quantity=480, rejected=5)
        self.assertEqual(res.data["progress"]["wip_sewing"], 15)
        self.assertEqual(self.entry(wo, stage="finishing", quantity=481).status_code, 400)
        res = self.entry(wo, stage="finishing", quantity=470, rejected=2)
        p = res.data["progress"]
        self.assertEqual((p["finished"], p["wip_finishing"], p["balance_to_finish"]), (470, 8, 530))

    def test_cut_allowance_per_size(self):
        wo = self.wo()   # 4Y planned 300, 3% allowance → 309
        self.assertEqual(self.entry(wo, stage="cutting", sizes={"4Y": 310}).status_code, 400)
        self.assertEqual(self.entry(wo, stage="cutting", sizes={"4Y": 309}).status_code, 201)
        self.assertEqual(self.entry(wo, stage="cutting", sizes={"XL": 5}).status_code, 400)

    def test_future_date_rejected(self):
        wo = self.wo()
        res = self.entry(wo, stage="cutting", sizes={"4Y": 10}, date=str(self.today + timedelta(days=1)))
        self.assertEqual(res.status_code, 400)

    def test_auto_complete_when_finished(self):
        wo = self.wo(quantity=100, sizes={"4Y": 30, "6Y": 40, "8Y": 30})
        self.entry(wo, stage="cutting", sizes={"4Y": 30, "6Y": 40, "8Y": 30})
        self.entry(wo, stage="sewing", quantity=100)
        res = self.entry(wo, stage="finishing", quantity=100)
        self.assertEqual(res.data["status"], "completed")
        self.assertEqual(self.entry(wo, stage="cutting", sizes={"4Y": 1}).status_code, 409)

    def test_manager_closes_short_with_reason(self):
        wo = self.wo()
        self.entry(wo, stage="cutting", sizes={"4Y": 100})
        self.assertEqual(self.client.post(f"/api/production-orders/{wo['id']}/complete/").status_code, 403)
        self.as_user(self.manager)
        self.assertEqual(self.client.post(f"/api/production-orders/{wo['id']}/complete/").status_code, 400)
        res = self.client.post(f"/api/production-orders/{wo['id']}/complete/", {"reason": "Buyer reduced quantity"})
        self.assertEqual(res.data["status"], "completed")

    def test_delete_entry_rules(self):
        wo = self.wo()
        self.entry(wo, stage="cutting", sizes={"4Y": 100})
        self.entry(wo, stage="sewing", quantity=80)
        cut_id = next(e["id"] for e in self.client.get(f"/api/production-orders/{wo['id']}/").data["entries"] if e["stage"] == "cutting")
        self.assertEqual(self.client.delete(f"/api/production-entries/{cut_id}/").status_code, 403)
        self.as_user(self.manager)
        self.assertEqual(self.client.delete(f"/api/production-entries/{cut_id}/").status_code, 409)   # sewing used it
        sew_id = next(e["id"] for e in self.client.get(f"/api/production-orders/{wo['id']}/").data["entries"] if e["stage"] == "sewing")
        self.assertEqual(self.client.delete(f"/api/production-entries/{sew_id}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/production-entries/{cut_id}/").status_code, 204)
        self.assertEqual(ProductionOrder.objects.get(pk=wo["id"]).status, "planned")

    def test_only_planned_can_be_edited_or_cancelled(self):
        wo = self.wo()
        res = self.client.patch(f"/api/production-orders/{wo['id']}/", {"smv": "15"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["capacity"]["daily_target"], 576)    # recalculated
        self.entry(wo, stage="cutting", sizes={"4Y": 10})
        self.assertEqual(self.client.patch(f"/api/production-orders/{wo['id']}/", {"smv": "10"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"/api/production-orders/{wo['id']}/cancel/").status_code, 409)

    def test_daily_report(self):
        wo = self.wo()
        self.entry(wo, stage="cutting", sizes={"4Y": 300, "6Y": 400})
        self.entry(wo, stage="sewing", quantity=540, rejected=6)
        res = self.client.get(f"/api/production-orders/daily/?date={self.today}")
        row = res.data["lines"][0]
        self.assertEqual((row["target"], row["sewn"], row["achievement_pct"]), (720, 540, 75.0))
        self.assertEqual(row["efficiency_pct"], 45.0)          # 540 × 12 ÷ (30 × 480)
        self.assertEqual(res.data["stages"]["cutting"]["good"], 700)

    def test_capacity_endpoint(self):
        res = self.client.get(f"/api/production-orders/capacity/?line={self.line.id}&smv=12&quantity=3000&start=2026-11-30")
        self.assertEqual((res.data["daily_target"], res.data["working_days"]), (720, 5))
        self.assertEqual(res.data["suggested_end"], date(2026, 12, 4))


class SizeOrderTests(SimpleTestCase):
    def test_garment_size_order(self):
        from .services import ordered_sizes
        self.assertEqual(ordered_sizes({"L": 1, "S": 1, "XL": 1, "M": 1}), ["S", "M", "L", "XL"])
        self.assertEqual(ordered_sizes({"12Y": 1, "2Y": 1, "10Y": 1, "4Y": 1}), ["2Y", "4Y", "10Y", "12Y"])
        self.assertEqual(ordered_sizes({"6-12M": 1, "0-3M": 1, "3-6M": 1}), ["0-3M", "3-6M", "6-12M"])
        self.assertEqual(ordered_sizes({"A": 1, "B": 1}, ["B", "A"]), ["B", "A"])     # tech pack order wins
