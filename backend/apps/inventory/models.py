"""
Stock and inventory.

Every change in stock is written as a StockMovement (a permanent ledger that is
never edited or deleted). StockLevel holds the running balance per product per
warehouse so lookups are fast. Both are only ever changed together, through
apps.inventory.services, inside a database transaction.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q


class Warehouse(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="warehouses")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["company", "name"]
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_warehouse_code_per_company")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class StockLevel(models.Model):
    product = models.ForeignKey("sales.Product", on_delete=models.PROTECT, related_name="stock_levels")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_levels")
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "warehouse__name"]
        constraints = [
            models.UniqueConstraint(fields=["product", "warehouse"], name="uniq_stock_level"),
            # The database itself refuses negative stock, even if the app has a bug.
            models.CheckConstraint(condition=Q(quantity__gte=0), name="stock_level_non_negative"),
        ]

    def __str__(self):
        return f"{self.product} @ {self.warehouse}: {self.quantity}"


class StockMovement(models.Model):
    class Type(models.TextChoices):
        RECEIPT = "receipt", "Receipt (goods in)"
        ISSUE = "issue", "Issue (goods out)"
        ADJUSTMENT = "adjustment", "Adjustment (stock count)"
        TRANSFER_OUT = "transfer_out", "Transfer out"
        TRANSFER_IN = "transfer_in", "Transfer in"
        SALE = "sale", "Sale"
        SALE_RETURN = "sale_return", "Sale reversed"

    product = models.ForeignKey("sales.Product", on_delete=models.PROTECT, related_name="stock_movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=2, help_text="Positive = in, negative = out")
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sales_order = models.ForeignKey(
        "sales.SalesOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements"
    )
    reference = models.CharField(max_length=100, blank=True, help_text="GRN no., transfer no., supplier bill no.")
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["product", "warehouse", "created_at"])]
        constraints = [
            models.CheckConstraint(condition=~Q(quantity=0), name="movement_quantity_non_zero"),
            models.CheckConstraint(condition=Q(balance_after__gte=0), name="movement_balance_non_negative"),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} {self.product} @ {self.warehouse}"
