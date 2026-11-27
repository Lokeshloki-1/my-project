from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.buyers.models import Buyer, CreditCheck
from apps.companies.models import Company
from apps.sales.models import Customer

from .models import OrderConfirmation


class MerchandisingTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        self.buyer = self._approved_buyer("Nordic Threads AB", limit="10000")
        self.client.force_authenticate(self.sales)

    def _approved_buyer(self, name, limit):
        customer = Customer.objects.create(company=self.company, name=name)
        buyer = Buyer.objects.create(
            company=self.company, legal_name=name, country="Sweden", preferred_currency="USD",
            status=Buyer.Status.APPROVED, customer=customer,
        )
        CreditCheck.objects.create(
            buyer=buyer, approved_limit=Decimal(limit), currency="USD", payment_terms="lc_sight",
            risk_rating="low", result="pass", checked_by=self.manager,
        )
        return buyer

    def as_user(self, user):
        self.client.force_authenticate(user)

    def cost_sheet(self, buyer=None, approve=True, **extra):
        body = {
            "buyer": (buyer or self.buyer).id, "style_no": "NT-101", "style_name": "Kids organic tee",
            "category": "kidswear", "quantity": 5000, "overhead_pct": "10", "margin_pct": "20", "commission_pct": "0",
            "lines": [
                {"category": "fabric", "description": "180 GSM organic jersey", "unit": "kg",
                 "consumption": "0.2", "rate": "5", "wastage_pct": "10"},   # 0.2*5*1.1 = 1.10
                {"category": "cmt", "description": "Cut, make, trim", "consumption": "1", "rate": "0.90"},  # 0.90
            ],
            **extra,
        }
        res = self.client.post("/api/cost-sheets/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        if approve:
            self.as_user(self.manager)
            res = self.client.post(f"/api/cost-sheets/{res.data['id']}/approve/")
            self.assertEqual(res.status_code, 200, res.data)
            self.as_user(self.sales)
        return res.data

    def quotation(self, sheet, quantity=1000, price=None, **extra):
        line = {"cost_sheet": sheet["id"], "quantity": quantity}
        if price is not None:
            line["unit_price"] = price
        res = self.client.post("/api/quotations/", {
            "buyer": self.buyer.id, "quote_date": str(timezone.localdate()), "lines": [line], **extra,
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def accepted_order(self, quantity=1000, price=None):
        quote = self.quotation(self.cost_sheet(), quantity=quantity, price=price)
        self.client.post(f"/api/quotations/{quote['id']}/send/")
        self.client.post(f"/api/quotations/{quote['id']}/accept/")
        res = self.client.post(f"/api/quotations/{quote['id']}/create-order/")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def fill_po(self, order_id):
        res = self.client.patch(f"/api/order-confirmations/{order_id}/", {
            "buyer_po_no": "PO-7788", "po_date": "2026-11-20", "ship_date": "2027-02-15",
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)

    # ---- costing
    def test_cost_sheet_calculation(self):
        sheet = self.cost_sheet(approve=False, commission_pct="5")
        self.assertEqual(sheet["lines"][0]["amount"], "1.1000")
        self.assertEqual(sheet["direct_cost"], "2.0000")       # 1.10 + 0.90
        self.assertEqual(sheet["overhead_amount"], "0.2000")   # 10%
        self.assertEqual(sheet["total_cost"], "2.2000")
        self.assertEqual(sheet["margin_amount"], "0.4400")     # 20%
        self.assertEqual(sheet["fob_price"], "2.78")           # 2.64 / 0.95 = 2.7789
        self.assertEqual(sheet["commission_amount"], "0.1389")
        self.assertEqual(sheet["currency"], "USD")             # from the buyer
        self.assertTrue(sheet["cost_no"].startswith("CS-"))

    def test_only_manager_approves_and_approved_is_locked(self):
        sheet = self.cost_sheet(approve=False)
        self.assertEqual(self.client.post(f"/api/cost-sheets/{sheet['id']}/approve/").status_code, 403)
        self.as_user(self.manager)
        self.client.post(f"/api/cost-sheets/{sheet['id']}/approve/")
        self.as_user(self.sales)
        res = self.client.patch(f"/api/cost-sheets/{sheet['id']}/", {"margin_pct": "50"}, format="json")
        self.assertEqual(res.status_code, 409)

    def test_cannot_approve_empty_cost_sheet(self):
        res = self.client.post("/api/cost-sheets/", {
            "buyer": self.buyer.id, "style_no": "X", "style_name": "Empty",
        }, format="json")
        self.as_user(self.manager)
        self.assertEqual(self.client.post(f"/api/cost-sheets/{res.data['id']}/approve/").status_code, 400)

    def test_copy_makes_a_draft_with_same_price(self):
        sheet = self.cost_sheet()
        res = self.client.post(f"/api/cost-sheets/{sheet['id']}/copy/")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "draft")
        self.assertEqual(res.data["fob_price"], sheet["fob_price"])
        self.assertEqual(len(res.data["lines"]), 2)

    def test_reopen_blocked_once_quoted(self):
        sheet = self.cost_sheet()
        quote = self.quotation(sheet)
        self.client.post(f"/api/quotations/{quote['id']}/send/")
        self.as_user(self.manager)
        self.assertEqual(self.client.post(f"/api/cost-sheets/{sheet['id']}/reopen/").status_code, 409)

    # ---- quotations
    def test_quotation_defaults_from_cost_sheet_and_buyer(self):
        quote = self.quotation(self.cost_sheet(), quantity=1000)
        line = quote["lines"][0]
        self.assertEqual(line["unit_price"], "2.64")
        self.assertEqual(line["style_no"], "NT-101")
        self.assertFalse(line["below_cost"])
        self.assertEqual(quote["total_amount"], "2640.00")
        self.assertEqual(quote["payment_terms"], "lc_sight")    # from the credit check
        self.assertEqual(quote["valid_until"], str(timezone.localdate() + timedelta(days=30)))
        self.assertEqual(quote["allowed_actions"], ["edit", "send", "cancel"])

    def test_below_cost_flag(self):
        quote = self.quotation(self.cost_sheet(), price="2.00")  # total cost is 2.20
        self.assertTrue(quote["lines"][0]["below_cost"])

    def test_quotation_needs_approved_buyer_and_cost_sheet(self):
        pending = Buyer.objects.create(company=self.company, legal_name="New Co", country="UK")
        res = self.client.post("/api/quotations/", {
            "buyer": pending.id, "quote_date": "2026-11-27", "lines": [],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("buyer", res.data)
        draft_sheet = self.cost_sheet(approve=False)
        res = self.client.post("/api/quotations/", {
            "buyer": self.buyer.id, "quote_date": "2026-11-27", "lines": [{"cost_sheet": draft_sheet["id"], "quantity": 10}],
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_cost_sheet_of_other_buyer_rejected(self):
        other = self._approved_buyer("Other AB", "100")
        sheet = self.cost_sheet(buyer=other)
        res = self.client.post("/api/quotations/", {
            "buyer": self.buyer.id, "quote_date": "2026-11-27", "lines": [{"cost_sheet": sheet["id"], "quantity": 10}],
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_quotation_flow_and_locking(self):
        quote = self.quotation(self.cost_sheet())
        qid = quote["id"]
        res = self.client.post(f"/api/quotations/{qid}/send/")
        self.assertEqual(res.data["status"], "sent")
        self.assertEqual(self.client.patch(f"/api/quotations/{qid}/", {"notes": "x"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"/api/quotations/{qid}/reject/", {}).status_code, 400)
        res = self.client.post(f"/api/quotations/{qid}/reopen/")
        self.assertEqual(res.data["status"], "draft")
        self.client.post(f"/api/quotations/{qid}/send/")
        res = self.client.post(f"/api/quotations/{qid}/accept/")
        self.assertEqual(res.data["status"], "accepted")
        self.assertEqual(res.data["allowed_actions"], ["create_order"])
        self.assertEqual([h["action"] for h in res.data["history"]], ["created", "sent", "reopened", "sent", "accepted"])

    def test_expired_quotation_cannot_be_accepted(self):
        quote = self.quotation(self.cost_sheet())
        self.client.post(f"/api/quotations/{quote['id']}/send/")
        from .models import Quotation
        Quotation.objects.filter(pk=quote["id"]).update(quote_date=date(2026, 1, 1), valid_until=date(2026, 1, 31))
        res = self.client.post(f"/api/quotations/{quote['id']}/accept/")
        self.assertEqual(res.status_code, 409)

    # ---- orders
    def test_create_order_copies_lines_and_is_idempotent(self):
        order = self.accepted_order(quantity=1000)
        self.assertEqual(order["status"], "draft")
        self.assertEqual(order["total_amount"], "2640.00")
        self.assertEqual(order["lines"][0]["style_no"], "NT-101")
        res = self.client.post(f"/api/quotations/{order['quotation']}/create-order/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(OrderConfirmation.objects.count(), 1)

    def test_confirm_needs_po_and_ship_date(self):
        order = self.accepted_order()
        OrderConfirmation.objects.filter(pk=order["id"]).update(ship_date=None)
        res = self.client.post(f"/api/order-confirmations/{order['id']}/confirm/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("buyer_po_no", res.data)
        self.assertIn("ship_date", res.data)

    def test_confirm_within_credit_limit(self):
        order = self.accepted_order(quantity=1000)  # 2,640 of 10,000
        self.fill_po(order["id"])
        self.assertTrue(self.client.get(f"/api/order-confirmations/{order['id']}/").data["credit"]["within_limit"])
        res = self.client.post(f"/api/order-confirmations/{order['id']}/confirm/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "confirmed")
        self.assertFalse(res.data["credit_override"])
        self.assertEqual(self.client.patch(f"/api/order-confirmations/{order['id']}/", {"notes": "x"}, format="json").status_code, 409)

    def test_over_credit_limit_needs_manager_with_reason(self):
        first = self.accepted_order(quantity=3000)  # 7,920
        self.fill_po(first["id"])
        self.client.post(f"/api/order-confirmations/{first['id']}/confirm/")
        second = self.accepted_order(quantity=1000)  # +2,640 = 10,560 > 10,000
        self.fill_po(second["id"])
        credit = self.client.get(f"/api/order-confirmations/{second['id']}/").data["credit"]
        self.assertEqual(credit["exposure"], Decimal("7920.00"))
        self.assertFalse(credit["within_limit"])

        res = self.client.post(f"/api/order-confirmations/{second['id']}/confirm/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["detail"].code, "credit_limit_exceeded")
        self.as_user(self.manager)
        self.assertEqual(self.client.post(f"/api/order-confirmations/{second['id']}/confirm/").status_code, 409)
        res = self.client.post(f"/api/order-confirmations/{second['id']}/confirm/",
                               {"override_reason": "LC received for the full value"})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["credit_override"])

    def test_cancel_confirmed_order_frees_credit_and_needs_manager(self):
        order = self.accepted_order(quantity=1000)
        self.fill_po(order["id"])
        self.client.post(f"/api/order-confirmations/{order['id']}/confirm/")
        self.assertEqual(self.client.post(f"/api/order-confirmations/{order['id']}/cancel/", {"reason": "x"}).status_code, 403)
        self.as_user(self.manager)
        res = self.client.post(f"/api/order-confirmations/{order['id']}/cancel/", {"reason": "Buyer withdrew PO"})
        self.assertEqual(res.data["status"], "cancelled")
        self.as_user(self.sales)
        nxt = self.accepted_order(quantity=1000)
        self.assertEqual(self.client.get(f"/api/order-confirmations/{nxt['id']}/").data["credit"]["exposure"], Decimal("0"))

    def test_orders_cannot_be_created_directly_or_deleted(self):
        order = self.accepted_order()
        self.assertEqual(self.client.post("/api/order-confirmations/", {}).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/order-confirmations/{order['id']}/").status_code, 405)

    def test_order_line_quantity_can_change_in_draft(self):
        order = self.accepted_order(quantity=1000)
        line = order["lines"][0]
        res = self.client.patch(f"/api/order-confirmations/{order['id']}/", {
            "lines": [{"cost_sheet": line["cost_sheet"], "quantity": 1200, "unit_price": line["unit_price"]}],
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["total_quantity"], 1200)
        self.assertEqual(res.data["total_amount"], "3168.00")
