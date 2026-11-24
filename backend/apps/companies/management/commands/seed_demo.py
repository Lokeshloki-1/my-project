"""
Fill the database with demo data so the dashboard has something to show.

    python manage.py seed_demo

Creates a demo admin login:  admin / admin12345  (change it!)
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Invoice, Payment
from apps.companies.models import Company
from apps.ddp.models import Shipment
from apps.employees.models import Department, Employee
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
                Product.objects.create(company=company, sku=f"P{i:03d}", name=name, unit_price=Decimal(price), hs_code=hs)
                for i, (name, price, hs) in enumerate([
                    ("Steel Valve 2in", 1850, "848180"), ("Copper Pipe 10m", 4200, "741110"),
                    ("Pump Motor 1HP", 12500, "841370"), ("Pressure Gauge", 950, "902620"),
                ])
            ]
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
                        salesperson=random.choice(employees), order_date=order_date,
                        status="draft" if target_status == "draft" else "confirmed",
                    )
                    for p in random.sample(products, random.randint(1, 3)):
                        SalesOrderItem.objects.create(
                            order=order, product=p, quantity=Decimal(random.randint(2, 20)),
                            unit_price=p.unit_price, tax_rate=p.tax_rate,
                        )
                    order.recalculate_totals()
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

        self.stdout.write(self.style.SUCCESS("Demo data created. Login: admin / admin12345"))

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
