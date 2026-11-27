from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.companies.models import Company

from .models import Sample, TechPack


class DevelopmentTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        self.buyer = Buyer.objects.create(company=self.company, legal_name="Nordic Threads AB", country="Sweden")
        self.client.force_authenticate(self.sales)

    def as_user(self, user):
        self.client.force_authenticate(user)

    def tech_pack(self, release=True, **extra):
        body = {
            "buyer": self.buyer.id, "style_no": "NT-101", "style_name": "Kids tee", "season": "SS27",
            "category": "kidswear", "sizes": ["4Y", "6Y", "8Y"], "base_size": "6Y", "colourways": ["Navy", "Red"],
            "measurements": [
                {"code": "A", "point": "Chest width", "tolerance": "1", "values": {"4Y": 32, "6Y": 34, "8Y": 36}},
                {"code": "B", "point": "Body length", "tolerance": "1.5", "values": {"4Y": 42, "6Y": 46, "8Y": 50}},
            ],
            "bom": [
                {"category": "fabric", "description": "180 GSM organic jersey", "consumption": "0.18", "unit": "kg"},
                {"category": "label", "description": "Main label", "placement": "Back neck"},
            ],
            **extra,
        }
        res = self.client.post("/api/tech-packs/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        if release:
            self.as_user(self.manager)
            res = self.client.post(f"/api/tech-packs/{res.data['id']}/release/")
            self.assertEqual(res.status_code, 200, res.data)
            self.as_user(self.sales)
        return res.data

    def sample(self, tp, sample_type="proto", **extra):
        res = self.client.post("/api/samples/", {
            "tech_pack": tp["id"], "sample_type": sample_type, "requested_on": "2026-11-27", "due_date": "2026-12-10",
            "colourway": "Navy", **extra,
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def to_sent(self, sample_id):
        self.client.post(f"/api/samples/{sample_id}/start/")
        self.client.post(f"/api/samples/{sample_id}/mark-ready/")
        res = self.client.post(f"/api/samples/{sample_id}/send/", {"courier": "DHL", "tracking_no": "123"})
        self.assertEqual(res.status_code, 200, res.data)
        return res.data

    # ---- tech packs
    def test_create_and_release(self):
        tp = self.tech_pack(release=False)
        self.assertTrue(tp["tp_no"].startswith("TP-"))
        self.assertEqual(tp["revision"], 1)
        self.assertEqual(tp["measurements"][0]["values"]["6Y"], "34")
        self.assertEqual(tp["missing_for_release"], [])
        self.assertEqual(self.client.post(f"/api/tech-packs/{tp['id']}/release/").status_code, 403)
        self.as_user(self.manager)
        res = self.client.post(f"/api/tech-packs/{tp['id']}/release/")
        self.assertEqual(res.data["status"], "released")
        self.assertIn("request_sample", res.data["allowed_actions"])

    def test_release_lists_missing(self):
        tp = self.tech_pack(release=False, measurements=[{"point": "Chest", "values": {"4Y": 32}}], bom=[])
        self.as_user(self.manager)
        res = self.client.post(f"/api/tech-packs/{tp['id']}/release/")
        self.assertEqual(res.status_code, 400)
        missing = " ".join(str(m) for m in res.data["missing"])
        self.assertIn("6Y, 8Y", missing)
        self.assertIn("fabric", missing)

    def test_measurement_validation(self):
        res = self.client.post("/api/tech-packs/", {
            "buyer": self.buyer.id, "style_no": "X", "style_name": "X", "sizes": ["S"],
            "measurements": [{"point": "Chest", "values": {"S": "abc"}}],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/tech-packs/", {
            "buyer": self.buyer.id, "style_no": "X", "style_name": "X", "sizes": ["S"], "base_size": "M",
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("base_size", res.data)

    def test_released_is_locked_and_revise_copies(self):
        tp = self.tech_pack()
        res = self.client.patch(f"/api/tech-packs/{tp['id']}/", {"season": "AW27"}, format="json")
        self.assertEqual(res.status_code, 409)
        res = self.client.post(f"/api/tech-packs/{tp['id']}/revise/", {"note": "Longer body"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["revision"], 2)
        self.assertEqual(res.data["tp_no"], tp["tp_no"])
        self.assertEqual(res.data["status"], "draft")
        self.assertEqual(len(res.data["measurements"]), 2)
        self.assertEqual(len(res.data["bom"]), 2)
        self.assertEqual(TechPack.objects.get(pk=tp["id"]).status, "superseded")
        again = self.client.post(f"/api/tech-packs/{tp['id']}/revise/")
        self.assertEqual(again.data["id"], res.data["id"])

    def test_rejected_buyer_cannot_get_tech_pack(self):
        self.buyer.status = Buyer.Status.REJECTED
        self.buyer.save()
        res = self.client.post("/api/tech-packs/", {"buyer": self.buyer.id, "style_no": "X", "style_name": "X"}, format="json")
        self.assertEqual(res.status_code, 400)

    # ---- samples
    def test_sample_needs_released_tech_pack(self):
        draft = self.tech_pack(release=False)
        res = self.client.post("/api/samples/", {"tech_pack": draft["id"], "sample_type": "proto", "requested_on": "2026-11-27"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_sample_defaults_and_validation(self):
        tp = self.tech_pack()
        s = self.sample(tp)
        self.assertEqual(s["size"], "6Y")       # base size
        self.assertEqual(s["round"], 1)
        self.assertTrue(s["sample_no"].startswith("SMP-"))
        res = self.client.post("/api/samples/", {"tech_pack": tp["id"], "sample_type": "fit", "requested_on": "2026-11-27", "size": "XL"}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/samples/", {"tech_pack": tp["id"], "sample_type": "fit", "requested_on": "2026-11-27", "colourway": "Pink"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_status_flow_and_wrong_steps(self):
        s = self.sample(self.tech_pack())
        self.assertEqual(self.client.post(f"/api/samples/{s['id']}/send/", {"courier": "DHL"}).status_code, 409)
        self.client.post(f"/api/samples/{s['id']}/start/")
        self.client.post(f"/api/samples/{s['id']}/mark-ready/")
        self.assertEqual(self.client.post(f"/api/samples/{s['id']}/send/", {}).status_code, 400)
        res = self.client.post(f"/api/samples/{s['id']}/send/", {"courier": "DHL", "tracking_no": "JD0001"})
        self.assertEqual(res.data["status"], "sent")
        self.assertEqual(res.data["allowed_actions"], ["decide", "measure"])
        self.assertEqual(self.client.patch(f"/api/samples/{s['id']}/", {"quantity": 3}, format="json").status_code, 409)

    def test_reject_needs_comments_and_resubmit_makes_round_two(self):
        s = self.sample(self.tech_pack(), sample_type="fit")
        self.to_sent(s["id"])
        self.assertEqual(self.client.post(f"/api/samples/{s['id']}/decide/", {"decision": "rejected"}).status_code, 400)
        res = self.client.post(f"/api/samples/{s['id']}/decide/", {"decision": "rejected", "comments": "Chest 2 cm too wide"})
        self.assertEqual(res.data["status"], "rejected")
        self.assertEqual(res.data["allowed_actions"], ["resubmit"])
        res = self.client.post(f"/api/samples/{s['id']}/resubmit/")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["round"], 2)
        self.assertIn("Chest 2 cm too wide", res.data["instructions"])
        again = self.client.post(f"/api/samples/{s['id']}/resubmit/")
        self.assertEqual(again.data["id"], res.data["id"])

    def test_pp_approval_approves_tech_pack_for_production(self):
        tp = self.tech_pack()
        proto = self.sample(tp, "proto")
        self.to_sent(proto["id"])
        self.client.post(f"/api/samples/{proto['id']}/decide/", {"decision": "approved"})
        self.assertFalse(TechPack.objects.get(pk=tp["id"]).production_approved)  # proto doesn't count
        pp = self.sample(tp, "pp")
        self.to_sent(pp["id"])
        res = self.client.post(f"/api/samples/{pp['id']}/decide/", {"decision": "approved_with_comments", "comments": "Use softer neck tape"})
        self.assertEqual(res.status_code, 200)
        tp_now = self.client.get(f"/api/tech-packs/{tp['id']}/").data
        self.assertTrue(tp_now["production_approved"])
        self.assertIn("approved_for_production", [h["action"] for h in tp_now["history"]])

    def test_measurements_checked_against_tolerance(self):
        tp = self.tech_pack()
        s = self.sample(tp)
        ids = {m["code"]: m["id"] for m in tp["measurements"]}
        res = self.client.put(f"/api/samples/{s['id']}/measurements/", {"readings": [
            {"measurement": ids["A"], "actual": "34.5"},   # spec 34 ±1 → ok
            {"measurement": ids["B"], "actual": "48"},     # spec 46 ±1.5 → out
        ]}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        rows = {m["code"]: m for m in res.data["measurements"]}
        self.assertTrue(rows["A"]["within_tolerance"])
        self.assertFalse(rows["B"]["within_tolerance"])
        self.assertEqual(rows["B"]["deviation"], "2.00")
        self.assertEqual(res.data["measurement_summary"], {"measured": 2, "out_of_tolerance": 1, "passed": False})

    def test_measurements_reject_other_tech_pack_points(self):
        tp = self.tech_pack()
        other = self.tech_pack(style_no="NT-999")
        s = self.sample(tp)
        res = self.client.put(f"/api/samples/{s['id']}/measurements/", {"readings": [
            {"measurement": other["measurements"][0]["id"], "actual": "30"}]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_rounds_count_across_revisions(self):
        tp = self.tech_pack()
        self.sample(tp, "fit")
        new = self.client.post(f"/api/tech-packs/{tp['id']}/revise/").data
        self.as_user(self.manager)
        self.client.post(f"/api/tech-packs/{new['id']}/release/")
        self.as_user(self.sales)
        self.assertEqual(self.sample(new, "fit")["round"], 2)

    def test_board_counts(self):
        tp = self.tech_pack()
        self.sample(tp)
        s2 = self.sample(tp, "fit")
        self.client.post(f"/api/samples/{s2['id']}/start/")
        counts = {r["status"]: r["count"] for r in self.client.get("/api/samples/board/").data}
        self.assertEqual(counts["requested"], 1)
        self.assertEqual(counts["in_progress"], 1)

    def test_only_unstarted_sample_can_be_deleted(self):
        tp = self.tech_pack()
        s = self.sample(tp)
        self.client.post(f"/api/samples/{s['id']}/start/")
        self.assertEqual(self.client.delete(f"/api/samples/{s['id']}/").status_code, 409)
        s2 = self.sample(tp)
        self.assertEqual(self.client.delete(f"/api/samples/{s2['id']}/").status_code, 204)
        self.assertEqual(Sample.objects.count(), 1)
