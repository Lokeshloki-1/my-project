from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.companies.models import Company
from apps.sales.models import Customer


class DDPShipmentTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(User.objects.create_user("u", password="pass12345!"))
        self.company = Company.objects.create(name="A", code="A")
        self.customer = Customer.objects.create(company=self.company, name="C", country="UAE")

    def test_landed_cost_calculation(self):
        res = self.client.post("/api/ddp/shipments/", {
            "company": self.company.id, "customer": self.customer.id, "destination_country": "UAE",
            "goods_value": "10000", "freight_cost": "1500", "insurance_cost": "500",
            "customs_duty_rate": "5", "import_vat_rate": "5", "other_charges": "400",
            "invoice_value": "15000",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        # CIF 12000 -> duty 600 -> VAT 5% of 12600 = 630 -> landed 12000+600+630+400
        self.assertEqual(res.data["cif_value"], "12000.00")
        self.assertEqual(res.data["customs_duty"], "600.00")
        self.assertEqual(res.data["import_vat"], "630.00")
        self.assertEqual(res.data["landed_cost"], "13630.00")
        self.assertEqual(res.data["margin"], "1370.00")
        self.assertEqual(res.data["incoterm"], "DDP")

    def test_quote_does_not_save(self):
        res = self.client.post("/api/ddp/shipments/quote/", {"goods_value": "1000", "customs_duty_rate": "10"}, format="json")
        self.assertEqual(res.data["landed_cost"], Decimal("1100.00"))
        self.assertEqual(self.client.get("/api/ddp/shipments/").data["count"], 0)

    def test_delivered_requires_date(self):
        res = self.client.post("/api/ddp/shipments/", {
            "company": self.company.id, "customer": self.customer.id, "destination_country": "UAE",
            "goods_value": "100", "status": "delivered",
        }, format="json")
        self.assertEqual(res.status_code, 400)
