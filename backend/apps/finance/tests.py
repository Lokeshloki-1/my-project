from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer, CreditCheck
from apps.companies.models import Company
from apps.exports.models import CartonGroup, ExportShipment, PackingList
from apps.inventory.models import Warehouse
from apps.merchandising.models import CostSheet, CostSheetLine, OrderConfirmation, OrderConfirmationLine, Quotation
from apps.production.models import ProductionLine, ProductionOrder
from apps.sales.models import Customer
from apps.stores import services as stores
from apps.stores.models import MaterialMovement

from .models import ExportInvoice


class FinanceTests(APITestCase):
    def setUp(self):
        self.acc = User.objects.create_user("acc", password="pass12345!", role=User.Role.ACCOUNTANT)
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        customer = Customer.objects.create(company=self.company, name="Nordic")
        self.buyer = Buyer.objects.create(company=self.company, legal_name="Nordic", country="SE", status="approved", customer=customer)
        CreditCheck.objects.create(buyer=self.buyer, approved_limit=Decimal("2000"), currency="USD", payment_terms="tt_30",
                                   risk_rating="low", result="pass", checked_by=self.manager)
        q = Quotation.objects.create(company=self.company, buyer=self.buyer, quote_date=date(2026, 11, 1), valid_until=date(2026, 12, 1), status="accepted")
        self.order = OrderConfirmation.objects.create(company=self.company, buyer=self.buyer, quotation=q, currency="USD", incoterm="FOB",
                                                      payment_terms="tt_30", buyer_po_no="PO1", ship_date=date(2027, 1, 10), status="confirmed")
        sheet = CostSheet.objects.create(company=self.company, buyer=self.buyer, style_no="NT-101", style_name="Tee", currency="USD")
        CostSheetLine.objects.create(cost_sheet=sheet, category="fabric", description="Jersey", consumption=Decimal("0.2"), rate=Decimal("5"))
        CostSheetLine.objects.create(cost_sheet=sheet, category="cmt", description="CMT", consumption=1, rate=Decimal("0.50"))
        CostSheetLine.objects.create(cost_sheet=sheet, category="packing", description="Polybag", consumption=1, rate=Decimal("0.10"))
        sheet.recalculate()   # direct 1.60 + 10% default overhead = total cost 1.76
        self.oline = OrderConfirmationLine.objects.create(order=self.order, cost_sheet=sheet, style_no="NT-101", description="Tee",
                                                          quantity=1000, unit_price=Decimal("3.00"))
        line = ProductionLine.objects.create(company=self.company, code="L1", name="Line 1")
        self.wo = ProductionOrder.objects.create(company=self.company, order=self.order, order_line=self.oline, style_no="NT-101",
                                                 quantity=1000, sizes={"M": 1000}, line=line, smv=Decimal("12"),
                                                 planned_start=date(2026, 11, 1), planned_end=date(2026, 11, 10), status="completed")
        self.shipment = self.shipped_shipment(cartons=40)    # 40 × 25 = 1000 pcs → USD 3000
        self.client.force_authenticate(self.acc)

    def shipped_shipment(self, cartons, status="shipped"):
        pl = PackingList.objects.create(company=self.company, order=self.order, pack_date=date(2026, 11, 20), status="finalized")
        CartonGroup.objects.create(packing_list=pl, production_order=self.wo, style_no="NT-101", from_carton=1, to_carton=cartons,
                                   sizes={"M": 25}, net_weight=5, gross_weight=6, length_cm=50, width_cm=40, height_cm=30)
        pl.recalculate()
        s = ExportShipment.objects.create(company=self.company, order=self.order, status=status,
                                          on_board_date=date(2026, 11, 22), invoice_date=date(2026, 11, 22))
        pl.shipment = s
        pl.save(update_fields=["shipment"])
        return s

    def invoice(self, rate="83.50", shipment=None):
        res = self.client.post("/api/export-invoices/create-from-shipment/", {"shipment": (shipment or self.shipment).id, "exchange_rate": rate})
        self.assertIn(res.status_code, (200, 201), res.data)
        return res.data

    def pay(self, inv, amount, charges="0", rate="84.00", received_on=None):
        return self.client.post("/api/export-receipts/", {"invoice": inv["id"], "received_on": received_on or str(timezone.localdate()),
                                                          "amount": amount, "bank_charges": charges, "exchange_rate": rate,
                                                          "method": "tt", "bank_reference": "FIRC-1"}, format="json")

    # ---- invoices
    def test_invoice_from_shipment(self):
        inv = self.invoice()
        self.assertEqual((inv["invoice_no"], inv["currency"], inv["amount"]), (self.shipment.invoice_no, "USD", "3000.00"))
        self.assertEqual(inv["amount_inr"], "250500.00")                       # 3000 × 83.50
        self.assertEqual(inv["due_date"], "2026-12-22")                        # TT 30 days
        self.assertEqual(inv["status"], "open")
        again = self.client.post("/api/export-invoices/create-from-shipment/", {"shipment": self.shipment.id, "exchange_rate": "90"})
        self.assertEqual((again.status_code, again.data["id"]), (200, inv["id"]))

    def test_invoice_needs_shipped_and_rate(self):
        booked = self.shipped_shipment(cartons=4, status="booked")
        self.assertEqual(self.client.post("/api/export-invoices/create-from-shipment/", {"shipment": booked.id, "exchange_rate": "83"}).status_code, 409)
        self.assertEqual(self.client.post("/api/export-invoices/create-from-shipment/", {"shipment": self.shipment.id}).status_code, 400)

    def test_sales_cannot_invoice(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.post("/api/export-invoices/create-from-shipment/", {"shipment": self.shipment.id, "exchange_rate": "83"}).status_code, 403)

    # ---- receipts
    def test_part_and_full_payment_with_gain(self):
        inv = self.invoice()
        res = self.pay(inv, "1000", charges="20", rate="84.00")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["amount_inr"], "84000.00")
        self.assertEqual(res.data["exchange_gain_loss_inr"], "510.00")           # 1020 × (84.00 − 83.50)
        inv = self.client.get(f"/api/export-invoices/{inv['id']}/").data
        self.assertEqual((inv["status"], inv["balance"]), ("partially_paid", "1980.00"))
        self.assertEqual(self.pay(inv, "1981").status_code, 400)                 # over balance
        res = self.pay(inv, "1980", rate="83.00")
        self.assertEqual(res.data["exchange_gain_loss_inr"], "-990.00")          # loss
        inv = self.client.get(f"/api/export-invoices/{inv['id']}/").data
        self.assertEqual((inv["status"], inv["balance"], inv["gain_loss_inr"]), ("paid", "0.00", Decimal("-480.00")))
        self.assertEqual(inv["allowed_actions"], [])

    def test_delete_receipt_is_manager_only_and_reopens(self):
        inv = self.invoice()
        rid = self.pay(inv, "3000").data["id"]
        self.assertEqual(self.client.delete(f"/api/export-receipts/{rid}/").status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.delete(f"/api/export-receipts/{rid}/").status_code, 204)
        self.assertEqual(ExportInvoice.objects.get(pk=inv["id"]).status, "open")

    def test_cancel_only_without_receipts(self):
        inv = self.invoice()
        self.pay(inv, "100")
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(f"/api/export-invoices/{inv['id']}/cancel/", {"reason": "x"}).status_code, 409)

    def test_future_receipt_rejected(self):
        inv = self.invoice()
        self.assertEqual(self.pay(inv, "10", received_on=str(timezone.localdate() + timedelta(days=1))).status_code, 400)

    # ---- receivables
    def test_ageing_buckets_and_credit(self):
        inv = self.invoice()
        old = timezone.localdate() - timedelta(days=75)
        ExportInvoice.objects.filter(pk=inv["id"]).update(invoice_date=old, due_date=old + timedelta(days=30))   # 45 days overdue
        second = self.invoice(shipment=self.shipped_shipment(cartons=4))       # 100 pcs → 300, not due
        self.pay(inv, "500")
        res = self.client.get("/api/export-invoices/ageing/").data
        self.assertEqual(res["totals"]["d31_60"], Decimal("208750.00"))      # 2500 × 83.50
        self.assertEqual(res["totals"]["not_due"], Decimal("25050.00"))      # 300 × 83.50
        buyer = res["by_buyer"][0]
        self.assertEqual((buyer["balance"], buyer["credit_limit"], buyer["over_limit"]), (Decimal("2800.00"), Decimal("2000.00"), True))
        self.assertEqual(res["invoices"][0]["days_overdue"], 45)
        s = self.client.get("/api/export-invoices/summary/").data
        self.assertEqual(s["overdue_invoices"], 1)
        self.assertEqual(second["status"], "open")

    # ---- profit
    def test_order_profit(self):
        wh = Warehouse.objects.create(company=self.company, code="RMS", name="Store")
        material = stores.material_for(self.company, "fabric", "Jersey", "", "kg")
        stock = stores._locked_stock(material, wh)
        stores._move(stock, Decimal("210"), MaterialMovement.Type.RECEIPT, self.manager, unit_cost=Decimal("400"))
        alloc = stores.allocate(self.order, material, wh, Decimal("200"), self.manager)
        stores.issue_allocation(alloc, self.manager)                            # 200 kg × 400 = 80,000 INR
        inv = self.invoice(rate="83.50")
        self.pay(inv, "2980", charges="20", rate="84.00")                       # gain (3000 × 0.5) = 1,500
        self.client.post("/api/order-expenses/", {"order": self.order.id, "date": "2026-11-23", "category": "freight", "amount_inr": "12000"})
        p = self.client.get(f"/api/order-profit/{self.order.id}/").data
        self.assertEqual(p["invoiced_inr"], Decimal("250500.00"))
        self.assertEqual(p["costs"]["materials_inr"], Decimal("80000.00"))
        self.assertEqual(p["costs"]["conversion_inr"], Decimal("50100.00"))    # (0.50 + 0.10) × 1000 × 83.50
        self.assertEqual(p["costs"]["bank_charges_inr"], Decimal("1670.00"))   # 20 × 83.50
        self.assertEqual(p["costs"]["expenses_inr"], Decimal("12000"))
        self.assertEqual(p["exchange_gain_loss_inr"], Decimal("1500.00"))
        self.assertEqual(p["profit_inr"], Decimal("108230.00"))               # 250500 − 143770 + 1500
        self.assertEqual(p["margin_pct"], Decimal("43.21"))
        self.assertEqual(p["planned_margin_pct"], Decimal("41.33"))           # (3.00 − 1.76) / 3.00; 1.76 = 1.60 + 10% overhead
        self.assertEqual((p["shipped_share_pct"], p["materials_in_wip_inr"]), (Decimal("100.00"), Decimal("0.00")))
        rows = self.client.get("/api/order-profit/").data
        self.assertEqual(rows[0]["profit_inr"], Decimal("108230.00"))

    def test_material_cost_matched_to_shipped_share(self):
        wh = Warehouse.objects.create(company=self.company, code="RMS", name="Store")
        material = stores.material_for(self.company, "fabric", "Jersey", "", "kg")
        stores._move(stores._locked_stock(material, wh), Decimal("200"), MaterialMovement.Type.RECEIPT, self.manager, unit_cost=Decimal("400"))
        stores.issue_allocation(stores.allocate(self.order, material, wh, Decimal("200"), self.manager), self.manager)
        self.invoice(shipment=self.shipped_shipment(cartons=10))       # only 250 of 1000 pcs invoiced
        p = self.client.get(f"/api/order-profit/{self.order.id}/").data
        self.assertEqual(p["shipped_share_pct"], Decimal("25.00"))
        self.assertEqual((p["materials_issued_inr"], p["costs"]["materials_inr"], p["materials_in_wip_inr"]),
                         (Decimal("80000.00"), Decimal("20000.00"), Decimal("60000.00")))
