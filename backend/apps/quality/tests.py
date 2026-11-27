from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.companies.models import Company
from apps.merchandising.models import CostSheet, OrderConfirmation, OrderConfirmationLine, Quotation
from apps.production.models import ProductionEntry, ProductionLine, ProductionOrder
from apps.sales.models import Customer

from . import aql
from .models import CorrectiveAction, DefectType, FinalInspection
from .services import ensure_default_defects


class AQLTableTests(SimpleTestCase):
    def test_common_garment_lots(self):
        self.assertEqual(aql.plan(1000, "2.5"), {"code": "J", "sample_size": 80, "accept": 5, "reject": 6})
        self.assertEqual(aql.plan(1000, "4.0")["accept"], 7)
        self.assertEqual(aql.plan(3000, "2.5")["sample_size"], 125)
        self.assertEqual(aql.plan(3000, "2.5")["accept"], 7)
        self.assertEqual(aql.plan(6000, "2.5"), {"code": "L", "sample_size": 200, "accept": 10, "reject": 11})
        self.assertEqual(aql.plan(6000, "4.0")["accept"], 14)
        self.assertEqual(aql.plan(200, "2.5")["accept"], 2)
        self.assertEqual(aql.plan(600000, "2.5")["sample_size"], 1250)

    def test_critical_and_small_lots(self):
        self.assertEqual(aql.plan(5000, "0")["accept"], 0)
        self.assertEqual(aql.plan(3, "2.5")["sample_size"], 2)
        self.assertEqual(aql.plan(5, "6.5")["sample_size"], 2)    # never more than the lot


class QualityTests(APITestCase):
    def setUp(self):
        self.qc = User.objects.create_user("qc", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        ensure_default_defects(self.company)
        self.d = {d.code: d.id for d in DefectType.objects.all()}
        customer = Customer.objects.create(company=self.company, name="Nordic")
        buyer = Buyer.objects.create(company=self.company, legal_name="Nordic", country="SE", status="approved", customer=customer)
        q = Quotation.objects.create(company=self.company, buyer=buyer, quote_date=date(2026, 11, 1), valid_until=date(2026, 12, 1), status="accepted")
        order = OrderConfirmation.objects.create(company=self.company, buyer=buyer, quotation=q, currency="USD", incoterm="FOB",
                                                 payment_terms="lc_sight", buyer_po_no="PO1", ship_date=date(2027, 3, 1), status="confirmed")
        sheet = CostSheet.objects.create(company=self.company, buyer=buyer, style_no="NT-101", style_name="Tee")
        oline = OrderConfirmationLine.objects.create(order=order, cost_sheet=sheet, style_no="NT-101", description="Tee", quantity=2000, unit_price=Decimal("3"))
        self.line = ProductionLine.objects.create(company=self.company, code="L1", name="Line 1")
        self.wo = ProductionOrder.objects.create(company=self.company, order=order, order_line=oline, style_no="NT-101", quantity=2000,
                                                 sizes={"M": 2000}, line=self.line, smv=Decimal("12"), planned_start=date(2026, 11, 20),
                                                 planned_end=date(2026, 11, 30), status="in_progress")
        ProductionEntry.objects.create(production_order=self.wo, stage="finishing", date=date(2026, 11, 25), quantity=1000)
        self.client.force_authenticate(self.qc)

    def inline(self, pieces=20, defective=1, defects=None, **extra):
        return self.client.post("/api/inline-inspections/", {
            "production_order": self.wo.id, "date": str(timezone.localdate()), "operation": "Side seam",
            "pieces_checked": pieces, "defective_pieces": defective,
            "defects": [{"defect_type": self.d[c], "count": n} for c, n in (defects if defects is not None else {"S01": 1}).items()], **extra,
        }, format="json")

    def final(self, lot=1000, **extra):
        res = self.client.post("/api/final-inspections/", {"production_order": self.wo.id, "inspection_date": "2026-11-27",
                                                           "lot_size": lot, "inspected_by_party": "Own QA", **extra}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    ALL_OK = {k: True for k, _ in FinalInspection.CHECKLIST}

    # ---- inline
    def test_inline_dhu_and_traffic_light(self):
        res = self.inline(pieces=40, defective=1, defects={"S01": 1})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data["dhu"], res.data["result"]), ("2.50", "green"))
        res = self.inline(pieces=40, defective=2, defects={"S01": 1, "S04": 1})
        self.assertEqual((res.data["dhu"], res.data["result"]), ("5.00", "amber"))
        self.assertIsNone(res.data["capa_id"])
        res = self.inline(pieces=20, defective=3, defects={"S03": 2, "S01": 2})
        self.assertEqual((res.data["dhu"], res.data["result"]), ("20.00", "red"))
        capa = CorrectiveAction.objects.get(pk=res.data["capa_id"])
        self.assertIn("DHU 20.00%", capa.problem)
        self.assertEqual(capa.status, "open")

    def test_inline_validation(self):
        self.assertEqual(self.inline(pieces=5, defective=6, defects={"S01": 6}).status_code, 400)
        self.assertEqual(self.inline(pieces=10, defective=3, defects={"S01": 2}).status_code, 400)
        self.assertEqual(self.inline(pieces=10, defective=0, defects={"S01": 2}).status_code, 400)
        res = self.inline(pieces=10, defective=0, defects={})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["result"], "green")

    def test_inline_needs_running_work_order(self):
        ProductionOrder.objects.filter(pk=self.wo.pk).update(status="completed")
        self.assertEqual(self.inline().status_code, 409)

    # ---- final
    def test_final_plan_from_lot_size(self):
        fi = self.final(lot=1000)
        self.assertEqual((fi["code_letter"], fi["sample_size"], fi["accept_major"], fi["accept_minor"]), ("J", 80, 5, 7))
        self.assertEqual(fi["finished_pcs"], 1000)
        res = self.client.post("/api/final-inspections/", {"production_order": self.wo.id, "inspection_date": "2026-11-27", "lot_size": 1200}, format="json")
        self.assertEqual(res.status_code, 400)   # more than finished

    def test_final_pass(self):
        fi = self.final()
        res = self.client.patch(f"/api/final-inspections/{fi['id']}/", {
            "checklist": self.ALL_OK, "defects": [{"defect_type": self.d["S01"], "severity": "major", "count": 5},
                                                  {"defect_type": self.d["P02"], "severity": "minor", "count": 7}]}, format="json")
        self.assertEqual((res.data["major_found"], res.data["minor_found"]), (5, 7))
        res = self.client.post(f"/api/final-inspections/{fi['id']}/submit/")
        self.assertEqual(res.data["status"], "passed", res.data)
        self.assertEqual(res.data["allowed_actions"], [])

    def test_final_fail_reasons_capa_and_reinspection(self):
        fi = self.final()
        self.client.patch(f"/api/final-inspections/{fi['id']}/", {
            "checklist": {**self.ALL_OK, "cartons": False},
            "defects": [{"defect_type": self.d["S01"], "severity": "major", "count": 6},
                        {"defect_type": self.d["F01"], "severity": "critical", "count": 1}]}, format="json")
        res = self.client.post(f"/api/final-inspections/{fi['id']}/submit/")
        self.assertEqual(res.data["status"], "failed")
        reasons = " ".join(res.data["fail_reasons"])
        self.assertIn("critical", reasons)
        self.assertIn("6 major defects, accept ≤ 5", reasons)
        self.assertIn("Carton marks", reasons)
        self.assertIsNotNone(res.data["capa_id"])
        self.assertEqual(self.client.patch(f"/api/final-inspections/{fi['id']}/", {"remarks": "x"}, format="json").status_code, 409)
        res = self.client.post(f"/api/final-inspections/{fi['id']}/reinspect/")
        self.assertEqual(res.status_code, 201)
        self.assertEqual((res.data["round"], res.data["status"], res.data["previous"]), (2, "draft", fi["id"]))
        again = self.client.post(f"/api/final-inspections/{fi['id']}/reinspect/")
        self.assertEqual(again.data["id"], res.data["id"])

    def test_checklist_must_be_answered(self):
        fi = self.final()
        self.assertEqual(self.client.post(f"/api/final-inspections/{fi['id']}/submit/").status_code, 400)

    # ---- CAPA & summary
    def test_close_capa(self):
        res = self.inline(pieces=10, defective=2, defects={"S03": 2})
        capa_id = res.data["capa_id"]
        self.assertEqual(self.client.post(f"/api/corrective-actions/{capa_id}/close/", {"root_cause": "x", "action": "y"}).status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/corrective-actions/{capa_id}/close/").status_code, 400)
        res = self.client.post(f"/api/corrective-actions/{capa_id}/close/", {"root_cause": "Worn needle on overlock", "action": "Needle changed; hourly checks"})
        self.assertEqual(res.data["status"], "closed")
        self.assertEqual(self.client.patch(f"/api/corrective-actions/{capa_id}/", {"owner": "x"}, format="json").status_code, 409)

    def test_summary_pareto_and_rates(self):
        self.inline(pieces=50, defective=3, defects={"S01": 3})
        self.inline(pieces=50, defective=1, defects={"S04": 1})
        fi = self.final()
        self.client.patch(f"/api/final-inspections/{fi['id']}/", {"checklist": self.ALL_OK,
                          "defects": [{"defect_type": self.d["S01"], "severity": "major", "count": 2}]}, format="json")
        self.client.post(f"/api/final-inspections/{fi['id']}/submit/")
        s = self.client.get("/api/quality-summary/").data
        self.assertEqual((s["inline"]["checks"], s["inline"]["pieces"], s["inline"]["defects"], s["inline"]["dhu"]), (2, 100, 4, 4.0))
        self.assertEqual(s["pareto"][0]["name"], "Broken stitch")
        self.assertEqual((s["pareto"][0]["inline"], s["pareto"][0]["final"], s["pareto"][0]["percent"]), (3, 2, 83.33))
        self.assertEqual(s["pareto"][-1]["cumulative_percent"], 100.0)
        self.assertEqual(s["final"]["pass_rate"], 100.0)
        self.assertEqual(s["by_line"][0]["dhu"], 4.0)
