from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.companies.models import Company
from apps.merchandising.models import CostSheet, OrderConfirmation, OrderConfirmationLine, Quotation
from apps.production.models import ProductionEntry, ProductionLine, ProductionOrder
from apps.quality.models import FinalInspection
from apps.sales.models import Customer

from .models import ExportDocument, PackingList
from .pdf import words_international


class ExportTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM", address="SIDCO", city="Tiruppur")
        customer = Customer.objects.create(company=self.company, name="Nordic")
        buyer = Buyer.objects.create(company=self.company, legal_name="Nordic Threads AB", country="Sweden", city="Stockholm",
                                     status="approved", customer=customer)
        q = Quotation.objects.create(company=self.company, buyer=buyer, quote_date=date(2026, 11, 1), valid_until=date(2026, 12, 1), status="accepted")
        self.order = OrderConfirmation.objects.create(company=self.company, buyer=buyer, quotation=q, currency="USD", incoterm="FOB",
                                                      payment_terms="lc_sight", buyer_po_no="PO-118", ship_date=date(2027, 2, 10), status="confirmed")
        sheet = CostSheet.objects.create(company=self.company, buyer=buyer, style_no="NT-101", style_name="Kids tee")
        oline = OrderConfirmationLine.objects.create(order=self.order, cost_sheet=sheet, style_no="NT-101", description="Kids tee",
                                                     quantity=1000, unit_price=Decimal("2.65"))
        line = ProductionLine.objects.create(company=self.company, code="L1", name="Line 1")
        self.wo = ProductionOrder.objects.create(company=self.company, order=self.order, order_line=oline, style_no="NT-101",
                                                 colourway="Navy", quantity=1000, sizes={"4Y": 500, "6Y": 500}, line=line, smv=Decimal("12"),
                                                 planned_start=date(2026, 11, 20), planned_end=date(2026, 11, 30), status="in_progress")
        ProductionEntry.objects.create(production_order=self.wo, stage="finishing", date=date(2026, 11, 25), quantity=960)
        self.client.force_authenticate(self.user)

    def passed(self, lot=960):
        FinalInspection.objects.create(company=self.company, production_order=self.wo, inspection_date=date(2026, 11, 26), lot_size=lot,
                                       code_letter="J", sample_size=80, accept_major=5, accept_minor=7, status="passed")

    def group(self, a, b, sizes=None, **extra):
        return {"production_order": self.wo.id, "from_carton": a, "to_carton": b, "sizes": sizes or {"4Y": 12, "6Y": 12},
                "net_weight": "5.0", "gross_weight": "5.6", "length_cm": "60", "width_cm": "40", "height_cm": "30", **extra}

    def packing_list(self, groups, finalize=True):
        res = self.client.post("/api/packing-lists/", {"order": self.order.id, "pack_date": "2026-11-27", "groups": groups}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        if finalize:
            res = self.client.post(f"/api/packing-lists/{res.data['id']}/finalize/")
            self.assertEqual(res.status_code, 200, res.data)
        return res.data

    def shipment(self, pl_ids, **extra):
        res = self.client.post("/api/export-shipments/", {"order": self.order.id, "mode": "sea", "packing_list_ids": pl_ids,
                                                          "port_of_discharge": "Gothenburg", "forwarder": "Kuehne+Nagel",
                                                          "etd": "2026-12-05", "eta": "2027-01-04", **extra}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    # ---- packing
    def test_needs_passed_final_inspection(self):
        res = self.client.post("/api/packing-lists/", {"order": self.order.id, "pack_date": "2026-11-27", "groups": [self.group(1, 10)]}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("no passed final inspection", str(res.data))

    def test_totals(self):
        self.passed()
        pl = self.packing_list([self.group(1, 30), self.group(31, 40, sizes={"4Y": 24})], finalize=False)
        self.assertEqual((pl["total_cartons"], pl["total_pcs"]), (40, 30 * 24 + 10 * 24))
        self.assertEqual(pl["net_weight"], "200.00")
        self.assertEqual(pl["gross_weight"], "224.00")
        self.assertEqual(pl["cbm"], "2.880")            # 0.072 m³ × 40
        status = pl["pack_status"][0]
        self.assertEqual((status["finished"], status["passed_inspection"], status["packable"]), (960, 960, 960))

    def test_cannot_pack_more_than_passed(self):
        self.passed(lot=500)
        res = self.client.post("/api/packing-lists/", {"order": self.order.id, "pack_date": "2026-11-27",
                                                       "groups": [self.group(1, 21)]}, format="json")   # 504 > 500
        self.assertEqual(res.status_code, 400)
        self.packing_list([self.group(1, 20)])                                          # 480 ok
        res = self.client.post("/api/packing-lists/", {"order": self.order.id, "pack_date": "2026-11-27",
                                                       "groups": [self.group(1, 1)]}, format="json")    # only 20 left
        self.assertEqual(res.status_code, 400)

    def test_carton_numbering(self):
        self.passed()
        res = self.client.post("/api/packing-lists/", {"order": self.order.id, "pack_date": "2026-11-27",
                                                       "groups": [self.group(1, 10), self.group(10, 12)]}, format="json")
        self.assertEqual(res.status_code, 400)                                          # overlap
        pl = self.packing_list([self.group(1, 10), self.group(12, 14)], finalize=False)
        self.assertEqual(self.client.post(f"/api/packing-lists/{pl['id']}/finalize/").status_code, 400)  # gap at 11
        pl = self.packing_list([self.group(2, 4)], finalize=False)
        self.assertEqual(self.client.post(f"/api/packing-lists/{pl['id']}/finalize/").status_code, 400)  # not from 1

    def test_finalized_locked_and_manager_reopens(self):
        self.passed()
        pl = self.packing_list([self.group(1, 5)])
        self.assertEqual(self.client.patch(f"/api/packing-lists/{pl['id']}/", {"notes": "x"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"/api/packing-lists/{pl['id']}/reopen/").status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/packing-lists/{pl['id']}/reopen/").data["status"], "draft")

    def test_unknown_size_rejected(self):
        self.passed()
        res = self.client.post("/api/packing-lists/", {"order": self.order.id, "pack_date": "2026-11-27",
                                                       "groups": [self.group(1, 2, sizes={"XL": 10})]}, format="json")
        self.assertEqual(res.status_code, 400)

    # ---- shipments
    def test_shipment_flow_and_documents(self):
        self.passed()
        pl = self.packing_list([self.group(1, 40)])
        s = self.shipment([pl["id"]], hs_codes={"NT-101": "61091000"})
        self.assertTrue(s["invoice_no"].startswith("CI-"))
        self.assertEqual(s["totals"]["pcs"], 960)
        self.assertEqual(s["invoice"]["total"], Decimal("2544.00"))         # 960 × 2.65
        docs = {d["doc_type"]: d for d in s["documents"]}
        self.assertEqual(len(docs), len(ExportDocument.DocType.choices))
        self.assertEqual(docs["commercial_invoice"]["status"], "ready")
        self.assertEqual(docs["packing_list"]["number"], pl["pl_no"])
        self.assertEqual(s["final_destination"], "Sweden")

        res = self.client.post(f"/api/export-shipments/{s['id']}/book/")
        self.assertEqual(res.data["status"], "booked")
        res = self.client.post(f"/api/export-shipments/{s['id']}/ship/")
        self.assertEqual(res.status_code, 400)
        for f in ("vessel", "bl_no", "shipping_bill_no", "container_type"):
            self.assertIn(f, res.data)
        self.client.patch(f"/api/export-shipments/{s['id']}/", {"vessel": "MSC Aurora", "voyage": "FA248", "container_type": "20GP",
                                                               "container_no": "MSCU1234567", "bl_no": "MEDU8812345",
                                                               "shipping_bill_no": "7712345", "shipping_bill_date": "2026-12-04"}, format="json")
        res = self.client.post(f"/api/export-shipments/{s['id']}/ship/", {"on_board_date": "2026-11-27"})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data["status"], res.data["invoice_date"]), ("shipped", "2026-11-27"))
        docs = {d["doc_type"]: d for d in res.data["documents"]}
        self.assertEqual((docs["bill_of_lading"]["number"], docs["bill_of_lading"]["status"]), ("MEDU8812345", "ready"))
        self.assertIn("pending", " ".join(res.data["warnings"]))
        self.assertEqual(self.client.patch(f"/api/export-shipments/{s['id']}/", {"vessel": "x"}, format="json").status_code, 409)
        self.assertEqual(self.client.patch(f"/api/export-shipments/{s['id']}/", {"notes": "Telex release"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"/api/export-shipments/{s['id']}/cancel/", {"reason": "x"}).status_code, 409)
        self.assertEqual(self.client.post(f"/api/export-shipments/{s['id']}/deliver/").data["status"], "delivered")
        # shipped packing lists can't be reopened
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/packing-lists/{pl['id']}/reopen/").status_code, 409)

    def test_book_needs_details(self):
        self.passed()
        pl = self.packing_list([self.group(1, 5)])
        s = self.shipment([pl["id"]], forwarder="", etd=None, eta=None)
        res = self.client.post(f"/api/export-shipments/{s['id']}/book/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("forwarder", res.data)
        self.assertIn("etd", res.data)

    def test_packing_list_on_one_shipment_only(self):
        self.passed()
        pl = self.packing_list([self.group(1, 5)])
        s = self.shipment([pl["id"]])
        res = self.client.post("/api/export-shipments/", {"order": self.order.id, "packing_list_ids": [pl["id"]]}, format="json")
        self.assertEqual(res.status_code, 400)
        self.client.post(f"/api/export-shipments/{s['id']}/cancel/", {"reason": "Vessel rolled"})
        self.assertIsNone(PackingList.objects.get(pk=pl["id"]).shipment_id)       # freed
        self.assertEqual(self.client.post("/api/export-shipments/", {"order": self.order.id, "packing_list_ids": [pl["id"]]}, format="json").status_code, 201)

    def test_draft_packing_list_cannot_ship(self):
        self.passed()
        pl = self.packing_list([self.group(1, 5)], finalize=False)
        res = self.client.post("/api/export-shipments/", {"order": self.order.id, "packing_list_ids": [pl["id"]]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_documents_update_and_pdfs(self):
        self.passed()
        pl = self.packing_list([self.group(1, 5)])
        s = self.shipment([pl["id"]])
        coo = next(d for d in s["documents"] if d["doc_type"] == "certificate_of_origin")
        res = self.client.patch(f"/api/export-documents/{coo['id']}/", {"number": "COO/2026/881", "date": "2026-12-03", "status": "ready"}, format="json")
        self.assertEqual(res.data["status"], "ready")
        r = self.client.get(f"/api/export-shipments/{s['id']}/commercial-invoice/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        r = self.client.get(f"/api/packing-lists/{pl['id']}/pdf/")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_etd_after_ship_date_warning(self):
        self.passed()
        pl = self.packing_list([self.group(1, 5)])
        s = self.shipment([pl["id"]], etd="2027-02-20", eta="2027-03-20")
        self.assertIn("after the agreed shipment date", " ".join(s["warnings"]))

    def test_amount_in_words(self):
        self.assertEqual(words_international(Decimal("12345.60"), "USD"),
                         "US Dollars Twelve Thousand Three Hundred Forty Five and Sixty Cents Only")
        self.assertEqual(words_international(Decimal("2000000"), "EUR"), "Euros Two Million Only")
