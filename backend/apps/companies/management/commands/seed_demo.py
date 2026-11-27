"""
Fill the database with demo data so the dashboard has something to show.

    python manage.py seed_demo

Creates demo logins (change them!):
    admin / admin12345        sales / sales12345
    manager / manager12345    accounts / accounts12345
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Invoice, Payment
from apps.buyers import services as buyer_services
from apps.buyers.models import Buyer, BuyerContact, BuyerEnquiry, BuyerRequirement
from apps.companies.models import Company
from apps.ddp.models import Shipment
from apps.employees.models import Department, Employee
from apps.inventory.models import StockMovement, Warehouse
from apps.inventory.services import issue_for_order, move_stock
from apps.sales.models import Customer, Product, SalesOrder, SalesOrderItem


class Command(BaseCommand):
    help = "Create demo companies, employees, customers, products, orders and DDP shipments."

    @transaction.atomic
    def handle(self, *args, **options):
        if Company.objects.exists():
            self.stdout.write(self.style.WARNING("Data already exists — skipping seed."))
            return
        random.seed(42)

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin12345", role=User.Role.ADMIN)
        for username, role in [("manager", User.Role.MANAGER), ("accounts", User.Role.ACCOUNTANT), ("sales", User.Role.SALES)]:
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(username, password=f"{username}12345", role=role, first_name=username.title())

        companies = [
            Company.objects.create(name="Hazpo Industries Pvt Ltd", code="HZP-IN", city="Chennai", country="India", currency="INR"),
            Company.objects.create(name="Hazpo Exports LLP", code="HZP-EX", city="Mumbai", country="India", currency="INR"),
        ]
        first_names = ["Arun", "Priya", "Karthik", "Divya", "Rahul", "Sneha", "Vijay", "Meena"]
        today = timezone.localdate()

        for ci, company in enumerate(companies):
            sales_dept = Department.objects.create(company=company, name="Sales")
            Department.objects.create(company=company, name="Accounts")
            employees = [
                Employee.objects.create(
                    company=company, department=sales_dept,
                    employee_code=f"{company.code}-E{i + 1:03d}",
                    first_name=first_names[ci * 4 + i], last_name="Kumar" if i % 2 else "Raj",
                    designation="Sales Executive", date_joined=date(2024, 1 + i, 1),
                    monthly_salary=Decimal(35000 + i * 5000),
                    monthly_sales_target=Decimal(300000 + i * 50000),
                )
                for i in range(4)
            ]
            customers = [
                Customer.objects.create(company=company, name=f"{n} Traders", city=c, country=country)
                for n, c, country in [
                    ("Sri Balaji", "Coimbatore", "India"), ("Global Mart", "Dubai", "UAE"),
                    ("Euro Supplies", "Hamburg", "Germany"), ("Lanka Retail", "Colombo", "Sri Lanka"),
                ]
            ]
            products = [
                Product.objects.create(
                    company=company, sku=f"P{i:03d}", name=name, unit_price=Decimal(price), hs_code=hs,
                    cost_price=(Decimal(price) * Decimal("0.65")).quantize(Decimal("0.01")), reorder_level=Decimal(reorder),
                )
                for i, (name, price, hs, reorder) in enumerate([
                    ("Steel Valve 2in", 1850, "848180", 50), ("Copper Pipe 10m", 4200, "741110", 40),
                    ("Pump Motor 1HP", 12500, "841370", 150), ("Pressure Gauge", 950, "902620", 60),
                ])
            ]
            city = "Chennai" if company.code == "HZP-IN" else "Mumbai"
            main_wh = Warehouse.objects.create(company=company, code="MAIN", name=f"{city} Main Warehouse", city=city)
            Warehouse.objects.create(company=company, code="DEPOT", name="Bengaluru Depot", city="Bengaluru")
            for p, qty in zip(products, [900, 700, 330, 1000]):
                move_stock(product=p, warehouse=main_wh, quantity=qty, movement_type=StockMovement.Type.RECEIPT,
                           unit_cost=p.cost_price, reference="OPENING", note="Opening stock")
            # 14 months of orders so reports have history
            for back in range(14):
                month_start = (today.replace(day=1) - timedelta(days=back * 30)).replace(day=1)
                for _ in range(random.randint(5, 10)):
                    day = random.randint(1, 28)
                    order_date = month_start.replace(day=day)
                    if order_date > today:
                        order_date = today
                    target_status = random.choice(["confirmed", "invoiced", "paid", "paid", "draft"])
                    order = SalesOrder.objects.create(
                        company=company, customer=random.choice(customers),
                        salesperson=random.choice(employees), order_date=order_date, warehouse=main_wh,
                        status="draft" if target_status == "draft" else "confirmed",
                    )
                    for p in random.sample(products, random.randint(1, 3)):
                        SalesOrderItem.objects.create(
                            order=order, product=p, quantity=Decimal(random.randint(2, 20)),
                            unit_price=p.unit_price, tax_rate=p.tax_rate,
                        )
                    order.recalculate_totals()
                    if order.status == "confirmed":
                        self._issue_with_restock(order)
                    if target_status in ("invoiced", "paid"):
                        self._invoice(order, paid=target_status == "paid", today=today)

            for order in SalesOrder.objects.filter(company=company, customer__country__in=["UAE", "Germany", "Sri Lanka"])[:5]:
                Shipment.objects.create(
                    company=company, sales_order=order, customer=order.customer,
                    destination_country=order.customer.country, mode=random.choice(["sea", "air"]),
                    carrier="Maersk" if random.random() > 0.5 else "DHL",
                    ship_date=order.order_date, expected_delivery=order.order_date + timedelta(days=21),
                    status=random.choice(["booked", "in_transit", "at_customs", "cleared"]),
                    goods_value=order.subtotal, freight_cost=Decimal("8500"), insurance_cost=Decimal("1200"),
                    customs_duty_rate=Decimal("5"), import_vat_rate=Decimal("5"), other_charges=Decimal("3000"),
                    invoice_value=(order.subtotal * Decimal("1.25")).quantize(Decimal("0.01")),
                )

        self._seed_buyers(companies[0], today)
        self.stdout.write(self.style.SUCCESS("Demo data created. Login: admin / admin12345"))

    def _seed_buyers(self, company, today):
        """Garment buyers at each onboarding stage, moved through the real workflow functions."""
        sales = User.objects.get(username="sales")
        accounts = User.objects.get(username="accounts")
        manager = User.objects.get(username="manager")
        rows = [
            # buyer, contact, country, city, source, categories, certifications, final stage
            ("Nordic Threads AB", "Anna Berg", "Sweden", "Stockholm", "trade_fair", ["knits", "kidswear"], ["GOTS", "OEKO-TEX"], "approved"),
            ("Maple Leaf Apparel Inc", "Liam Tremblay", "Canada", "Toronto", "email", ["wovens"], ["BSCI"], "pending_approval"),
            ("Bayside Retail Ltd", "Olivia Smith", "United Kingdom", "Leeds", "website", ["denim"], ["WRAP", "SEDEX"], "pending_credit"),
            ("Sonnen Mode GmbH", "Jonas Weber", "Germany", "Munich", "agent", ["activewear"], ["OEKO-TEX"], "credit_failed"),
            ("Pacific Home Co", "Mia Chen", "Australia", "Sydney", "referral", ["home_textiles"], ["OEKO-TEX"], "registered"),
            ("Iberia Kids SL", "Lucia Garcia", "Spain", "Madrid", "trade_fair", ["kidswear"], ["GOTS"], "enquiry"),
            ("Atlas Fashion LLC", "Omar Haddad", "UAE", "Dubai", "email", ["knits"], [], "enquiry"),
        ]
        for i, (name, contact, country, city, source, cats, certs, stage) in enumerate(rows):
            enquiry = BuyerEnquiry.objects.create(
                company=company, source=source, buyer_name=name, contact_name=contact,
                email=f"{contact.split()[0].lower()}@{name.split()[0].lower()}.example", country=country,
                product_interest=", ".join(cats), expected_volume=20000 + i * 15000,
                received_on=today - timedelta(days=40 - i * 5), assigned_to=sales,
                status="qualified" if i % 2 else "new",
            )
            if stage == "enquiry":
                continue
            buyer, _ = buyer_services.convert_enquiry(enquiry, sales)
            Buyer.objects.filter(pk=buyer.pk).update(
                city=city, address=f"{10 + i} Harbour Street, {city}", buyer_type=random.choice(["brand", "retailer", "importer"]),
                preferred_currency="EUR" if country in ("Germany", "Spain") else "USD", default_incoterm="FOB",
            )
            buyer.refresh_from_db()
            BuyerContact.objects.create(buyer=buyer, name="Accounts Desk", department="accounts",
                                        email=f"accounts@{name.split()[0].lower()}.example")
            BuyerRequirement.objects.create(
                buyer=buyer, product_categories=cats, certifications=certs, gsm_min=140, gsm_max=240,
                fabric_composition="100% cotton", size_range="XS-XXL", annual_volume=enquiry.expected_volume,
                target_price_min=Decimal("3.50"), target_price_max=Decimal("7.00"), price_currency=buyer.preferred_currency,
                delivery_port="Chennai", testing_lab="SGS",
            )
            if stage == "registered":
                continue
            buyer_services.submit_buyer(buyer, sales)
            if stage == "pending_credit":
                continue
            passed = stage != "credit_failed"
            buyer_services.record_credit_check(
                buyer, accounts, requested_limit=Decimal("75000"), approved_limit=Decimal("60000") if passed else 0,
                currency="USD", payment_terms="lc_sight" if passed else "advance", risk_rating="low" if passed else "high",
                result="pass" if passed else "fail", bank_reference="Bank confirms account in good standing" if passed else "",
                remarks="" if passed else "Two trade references reported late payments",
            )
            if stage == "approved":
                buyer_services.approve_buyer(buyer, manager)

    def _issue_with_restock(self, order):
        """Take stock for the order; if a product is short, record a restock receipt first (like a purchase)."""
        for item in order.items.select_related("product"):
            level = item.product.stock_levels.filter(warehouse=order.warehouse).first()
            available = level.quantity if level else Decimal("0")
            if available < item.quantity:
                move_stock(product=item.product, warehouse=order.warehouse, quantity=Decimal("200"),
                           movement_type=StockMovement.Type.RECEIPT, unit_cost=item.product.cost_price,
                           reference=f"GRN-{order.order_date:%y%m}", note="Restock from supplier")
        issue_for_order(order)

    def _invoice(self, order, paid, today):
        invoice = Invoice.objects.create(
            sales_order=order, company=order.company, customer=order.customer,
            invoice_date=order.order_date, due_date=order.order_date + timedelta(days=30),
            subtotal=order.subtotal, tax_amount=order.tax_amount, total=order.total,
        )
        order.status = SalesOrder.Status.INVOICED
        order.save(update_fields=["status"])
        pay_date = min(order.order_date + timedelta(days=random.randint(5, 40)), today)
        if paid:
            Payment.objects.create(invoice=invoice, payment_date=pay_date, amount=invoice.total,
                                   method=random.choice(["bank_transfer", "upi", "cheque"]),
                                   reference=f"UTR{random.randint(10**9, 10**10)}")
        elif random.random() < 0.4:
            Payment.objects.create(invoice=invoice, payment_date=pay_date,
                                   amount=(invoice.total / 2).quantize(Decimal("0.01")),
                                   method="bank_transfer", reference=f"UTR{random.randint(10**9, 10**10)}")
        invoice.refresh_payment_status()
