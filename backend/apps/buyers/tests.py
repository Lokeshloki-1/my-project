from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.companies.models import Company
from apps.sales.models import Customer

from .models import Buyer, BuyerEnquiry


class BuyerOnboardingTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sal", password="pass12345!", role=User.Role.SALES)
        self.accountant = User.objects.create_user("acc", password="pass12345!", role=User.Role.ACCOUNTANT)
        self.manager = User.objects.create_user("mgr", password="pass12345!", role=User.Role.MANAGER)
        self.company = Company.objects.create(name="Tex Mills", code="TM")
        self.client.force_authenticate(self.sales)

    # ---- helpers
    def as_user(self, user):
        self.client.force_authenticate(user)

    def new_enquiry(self, **extra):
        body = {
            "company": self.company.id, "buyer_name": "Nordic Wear AB", "contact_name": "Anna Berg",
            "email": "anna@nordic.example", "country": "Sweden", "received_on": "2026-11-01",
            "product_interest": "Organic knit tees", **extra,
        }
        res = self.client.post("/api/buyer-enquiries/", body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def new_buyer(self):
        res = self.client.post("/api/buyers/", {
            "company": self.company.id, "legal_name": "Coastline Retail Ltd", "country": "United Kingdom",
            "city": "Leeds", "address": "1 Mill Road", "tax_id": "GB123456789", "preferred_currency": "gbp",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def complete(self, buyer_id):
        res = self.client.post("/api/buyer-contacts/", {
            "buyer": buyer_id, "name": "Sam Lee", "email": "sam@coast.example", "department": "sourcing",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        res = self.client.post("/api/buyer-requirements/", {
            "buyer": buyer_id, "product_categories": ["knits", "kidswear"], "gsm_min": 160, "gsm_max": 220,
            "certifications": ["GOTS", "OEKO-TEX"],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)

    def credit(self, buyer_id, result="pass", limit="50000"):
        return self.client.post("/api/credit-checks/", {
            "buyer": buyer_id, "requested_limit": "60000", "approved_limit": limit, "currency": "USD",
            "payment_terms": "lc_sight", "risk_rating": "low", "result": result,
        }, format="json")

    def ready_for_approval(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        self.assertEqual(self.client.post(f"/api/buyers/{buyer['id']}/submit/").status_code, 200)
        self.as_user(self.accountant)
        self.assertEqual(self.credit(buyer["id"]).status_code, 201)
        self.as_user(self.manager)
        return buyer["id"]

    # ---- tests
    def test_full_flow_from_enquiry_to_customer(self):
        enquiry = self.new_enquiry()
        self.assertTrue(enquiry["enquiry_no"].startswith("ENQ-2026-"))

        res = self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/convert/")
        self.assertEqual(res.status_code, 201, res.data)
        buyer = res.data
        self.assertEqual(buyer["status"], "registered")
        self.assertEqual(buyer["legal_name"], "Nordic Wear AB")
        self.assertEqual(len(buyer["contacts"]), 1)
        self.assertTrue(buyer["contacts"][0]["is_primary"])
        self.assertIn("submit", buyer["allowed_actions"])
        self.assertTrue(buyer["onboarding"][0]["done"])  # came from an enquiry

        bid = buyer["id"]
        self.client.patch(f"/api/buyers/{bid}/", {"city": "Stockholm", "address": "Gatan 1"}, format="json")
        self.client.post("/api/buyer-requirements/", {"buyer": bid, "product_categories": ["knits"]}, format="json")
        res = self.client.post(f"/api/buyers/{bid}/submit/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "pending_credit")

        self.as_user(self.accountant)
        self.assertEqual(self.credit(bid).status_code, 201)
        self.as_user(self.manager)
        res = self.client.post(f"/api/buyers/{bid}/approve/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "approved")
        self.assertTrue(all(step["done"] for step in res.data["onboarding"]))

        customer = Customer.objects.get(pk=res.data["customer_id"])
        self.assertEqual(customer.name, "Nordic Wear AB")
        self.assertEqual(customer.email, "anna@nordic.example")
        self.assertEqual(customer.company, self.company)

        timeline = self.client.get(f"/api/buyers/{bid}/timeline/").data
        self.assertEqual([t["to_status"] for t in timeline],
                         ["registered", "pending_credit", "pending_approval", "approved"])
        self.assertEqual(BuyerEnquiry.objects.get(pk=enquiry["id"]).status, "converted")

    def test_convert_twice_returns_same_buyer(self):
        enquiry = self.new_enquiry()
        first = self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/convert/")
        second = self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/convert/")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Buyer.objects.count(), 1)

    def test_rejected_enquiry_cannot_be_converted(self):
        enquiry = self.new_enquiry()
        self.assertEqual(self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/reject/", {}).status_code, 400)
        res = self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/reject/", {"reason": "Volume too small"})
        self.assertEqual(res.data["status"], "rejected")
        res = self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/convert/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["detail"].code, "invalid_transition")

    def test_enquiry_status_cannot_be_set_to_converted_by_hand(self):
        enquiry = self.new_enquiry()
        res = self.client.patch(f"/api/buyer-enquiries/{enquiry['id']}/", {"status": "converted"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_submit_lists_missing_steps(self):
        buyer = self.client.post("/api/buyers/", {
            "company": self.company.id, "legal_name": "Bare Ltd", "country": "UK",
        }, format="json").data
        res = self.client.post(f"/api/buyers/{buyer['id']}/submit/")
        self.assertEqual(res.status_code, 400)
        missing = [str(m) for m in res.data["missing"]]
        self.assertIn("Address", missing)
        self.assertIn("At least one contact", missing)
        self.assertIn("Buyer requirements", missing)

    def test_status_is_not_writable(self):
        buyer = self.new_buyer()
        self.client.patch(f"/api/buyers/{buyer['id']}/", {"status": "approved"}, format="json")
        self.assertEqual(Buyer.objects.get(pk=buyer["id"]).status, "registered")

    def test_profile_locked_after_submit_for_sales_but_not_manager(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        self.client.post(f"/api/buyers/{buyer['id']}/submit/")
        res = self.client.patch(f"/api/buyers/{buyer['id']}/", {"city": "York"}, format="json")
        self.assertEqual(res.status_code, 409)
        res = self.client.post("/api/buyer-contacts/", {"buyer": buyer["id"], "name": "X", "phone": "1"}, format="json")
        self.assertEqual(res.status_code, 409)
        self.as_user(self.manager)
        res = self.client.patch(f"/api/buyers/{buyer['id']}/", {"city": "York"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)

    def test_sales_cannot_record_credit_or_approve(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        self.client.post(f"/api/buyers/{buyer['id']}/submit/")
        self.assertEqual(self.credit(buyer["id"]).status_code, 403)
        self.assertNotIn("record_credit_check", self.client.get(f"/api/buyers/{buyer['id']}/").data["allowed_actions"])
        bid = self.ready_for_approval()
        self.as_user(self.sales)
        self.assertEqual(self.client.post(f"/api/buyers/{bid}/approve/").status_code, 403)
        self.as_user(self.accountant)
        self.assertEqual(self.client.post(f"/api/buyers/{bid}/approve/").status_code, 403)

    def test_credit_check_only_when_pending_credit(self):
        buyer = self.new_buyer()
        self.as_user(self.accountant)
        self.assertEqual(self.credit(buyer["id"]).status_code, 409)

    def test_failed_credit_blocks_approval_and_allows_resubmit(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        self.client.post(f"/api/buyers/{buyer['id']}/submit/")
        self.as_user(self.accountant)
        res = self.credit(buyer["id"], result="fail", limit="50000")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["approved_limit"], "0.00")  # forced to zero on fail
        self.as_user(self.manager)
        res = self.client.post(f"/api/buyers/{buyer['id']}/approve/")
        self.assertEqual(res.status_code, 409)
        self.assertFalse(Customer.objects.exists())
        self.as_user(self.sales)
        self.client.patch(f"/api/buyers/{buyer['id']}/", {"bank_name": "HSBC"}, format="json")
        res = self.client.post(f"/api/buyers/{buyer['id']}/submit/")
        self.assertEqual(res.data["status"], "pending_credit")

    def test_passed_credit_needs_a_limit(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        self.client.post(f"/api/buyers/{buyer['id']}/submit/")
        self.as_user(self.accountant)
        self.assertEqual(self.credit(buyer["id"], limit="0").status_code, 400)

    def test_approve_twice_creates_one_customer(self):
        bid = self.ready_for_approval()
        first = self.client.post(f"/api/buyers/{bid}/approve/")
        second = self.client.post(f"/api/buyers/{bid}/approve/")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["customer_id"], second.data["customer_id"])
        self.assertEqual(Customer.objects.count(), 1)

    def test_reject_and_reopen(self):
        bid = self.ready_for_approval()
        self.assertEqual(self.client.post(f"/api/buyers/{bid}/reject/", {}).status_code, 400)
        res = self.client.post(f"/api/buyers/{bid}/reject/", {"reason": "Sanctioned country"})
        self.assertEqual(res.data["status"], "rejected")
        self.assertEqual(res.data["allowed_actions"], ["reopen"])
        res = self.client.post(f"/api/buyers/{bid}/reopen/")
        self.assertEqual(res.data["status"], "registered")
        self.assertEqual(self.client.post(f"/api/buyers/{bid}/approve/").status_code, 409)

    def test_only_one_primary_contact(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        res = self.client.post("/api/buyer-contacts/", {
            "buyer": buyer["id"], "name": "New Boss", "email": "boss@coast.example", "is_primary": True,
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        contacts = self.client.get(f"/api/buyer-contacts/?buyer={buyer['id']}").data["results"]
        self.assertEqual([c["name"] for c in contacts if c["is_primary"]], ["New Boss"])
        # Deleting the primary promotes the remaining contact.
        self.client.delete(f"/api/buyer-contacts/{res.data['id']}/")
        contacts = self.client.get(f"/api/buyer-contacts/?buyer={buyer['id']}").data["results"]
        self.assertTrue(contacts[0]["is_primary"])

    def test_contact_needs_email_or_phone(self):
        buyer = self.new_buyer()
        res = self.client.post("/api/buyer-contacts/", {"buyer": buyer["id"], "name": "Ghost"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_requirement_validation(self):
        buyer = self.new_buyer()
        res = self.client.post("/api/buyer-requirements/", {
            "buyer": buyer["id"], "product_categories": ["spaceships"],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/buyer-requirements/", {
            "buyer": buyer["id"], "gsm_min": 300, "gsm_max": 100,
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("gsm_max", res.data)

    def test_only_registered_buyer_without_credit_history_can_be_deleted(self):
        enquiry = self.new_enquiry()
        buyer = self.client.post(f"/api/buyer-enquiries/{enquiry['id']}/convert/").data
        self.assertEqual(self.client.delete(f"/api/buyers/{buyer['id']}/").status_code, 204)
        self.assertEqual(BuyerEnquiry.objects.get(pk=enquiry["id"]).status, "qualified")
        bid = self.ready_for_approval()
        self.assertEqual(self.client.delete(f"/api/buyers/{bid}/").status_code, 409)

    def test_credit_checks_cannot_be_edited_or_deleted(self):
        bid = self.ready_for_approval()
        check_id = self.client.get(f"/api/credit-checks/?buyer={bid}").data["results"][0]["id"]
        self.assertEqual(self.client.patch(f"/api/credit-checks/{check_id}/", {"result": "fail"}).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/credit-checks/{check_id}/").status_code, 405)

    def test_pipeline_counts(self):
        self.new_buyer()
        self.ready_for_approval()
        self.new_enquiry()
        res = self.client.get("/api/buyers/pipeline/")
        counts = {s["status"]: s["count"] for s in res.data["stages"]}
        self.assertEqual(counts["registered"], 1)
        self.assertEqual(counts["pending_approval"], 1)
        self.assertEqual(res.data["total"], 2)
        self.assertEqual(res.data["open_enquiries"], 1)

    def test_list_has_primary_contact(self):
        buyer = self.new_buyer()
        self.complete(buyer["id"])
        row = self.client.get("/api/buyers/").data["results"][0]
        self.assertEqual(row["primary_contact"]["name"], "Sam Lee")
        self.assertEqual(row["preferred_currency"], "GBP")
