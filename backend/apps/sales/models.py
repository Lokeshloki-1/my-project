from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import Q

TWO_PLACES = Decimal("0.01")


class Customer(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="customers")
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    tax_id = models.CharField("GSTIN / Tax ID", max_length=30, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="products")
    sku = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    hs_code = models.CharField("HS code", max_length=20, blank=True, help_text="Customs tariff code, used for DDP shipments")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"), help_text="Percent, e.g. 18 for 18% GST")
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Purchase cost, used for stock value")
    reorder_level = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="Warn when total stock falls to or below this"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "sku"], name="uniq_sku_per_company"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="product_price_non_negative"),
            models.CheckConstraint(condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100), name="product_tax_rate_0_100"),
            models.CheckConstraint(condition=Q(cost_price__gte=0), name="product_cost_non_negative"),
            models.CheckConstraint(condition=Q(reorder_level__gte=0), name="product_reorder_non_negative"),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"


class SalesOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        INVOICED = "invoiced", "Invoiced"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    # Only these statuses count as real revenue in reports.
    REVENUE_STATUSES = [Status.CONFIRMED, Status.INVOICED, Status.PAID]

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="sales_orders")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    salesperson = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, null=True, blank=True, related_name="sales_orders"
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, null=True, blank=True, related_name="sales_orders",
        help_text="Stock is taken from here when the order is confirmed. Leave empty for services.",
    )
    order_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    order_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-order_date", "-id"]
        indexes = [models.Index(fields=["company", "order_date"])]

    def __str__(self):
        return self.order_no or f"Draft #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.order_no:
            # Derived from the primary key, so it is unique without race conditions.
            self.order_no = f"SO-{self.order_date:%Y}-{self.pk:06d}"
            super().save(update_fields=["order_no"])

    def recalculate_totals(self):
        subtotal = Decimal("0")
        tax = Decimal("0")
        for item in self.items.all():
            subtotal += item.line_subtotal
            tax += item.line_tax
        self.subtotal = subtotal.quantize(TWO_PLACES, ROUND_HALF_UP)
        self.tax_amount = tax.quantize(TWO_PLACES, ROUND_HALF_UP)
        self.total = self.subtotal + self.tax_amount
        self.save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])


class SalesOrderItem(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="item_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="item_price_non_negative"),
        ]

    @property
    def line_subtotal(self):
        return (self.quantity * self.unit_price).quantize(TWO_PLACES, ROUND_HALF_UP)

    @property
    def line_tax(self):
        return (self.line_subtotal * self.tax_rate / 100).quantize(TWO_PLACES, ROUND_HALF_UP)

    @property
    def line_total(self):
        return self.line_subtotal + self.line_tax
