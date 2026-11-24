"""
DDP (Delivered Duty Paid) shipments.

Under DDP the seller (your company) pays every cost until the goods reach the
customer: freight, insurance, import customs duty and import VAT/GST.
This module records those costs and calculates the landed cost and margin.

    CIF value     = goods value + freight + insurance
    customs duty  = CIF value * duty rate %
    import VAT    = (CIF value + customs duty) * VAT rate %
    landed cost   = CIF value + customs duty + import VAT + other charges
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import Q

TWO_PLACES = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(TWO_PLACES, ROUND_HALF_UP)


class Shipment(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        IN_TRANSIT = "in_transit", "In transit"
        AT_CUSTOMS = "at_customs", "At customs"
        CLEARED = "cleared", "Customs cleared"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class Mode(models.TextChoices):
        SEA = "sea", "Sea"
        AIR = "air", "Air"
        ROAD = "road", "Road"
        RAIL = "rail", "Rail"
        COURIER = "courier", "Courier"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="shipments")
    sales_order = models.ForeignKey(
        "sales.SalesOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="shipments"
    )
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="shipments")
    shipment_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    incoterm = models.CharField(max_length=3, default="DDP", editable=False)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SEA)
    carrier = models.CharField(max_length=100, blank=True)
    tracking_no = models.CharField(max_length=100, blank=True)
    origin_country = models.CharField(max_length=100, default="India")
    destination_country = models.CharField(max_length=100)
    destination_address = models.TextField(blank=True)

    ship_date = models.DateField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    delivered_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED, db_index=True)

    currency = models.CharField(max_length=3, default="INR")
    goods_value = models.DecimalField(max_digits=14, decimal_places=2, help_text="Value of goods being shipped")
    freight_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    insurance_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    customs_duty_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="% of CIF value")
    import_vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="% of (CIF + duty)")
    other_charges = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text="Clearing agent, port, handling, last-mile, etc."
    )
    invoice_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text="Amount charged to the customer (DDP price)"
    )

    # Calculated on save — never sent by the client.
    customs_duty = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    import_vat = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    landed_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(goods_value__gte=0) & Q(freight_cost__gte=0) & Q(insurance_cost__gte=0)
                & Q(other_charges__gte=0) & Q(invoice_value__gte=0),
                name="shipment_amounts_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(customs_duty_rate__gte=0) & Q(customs_duty_rate__lte=100)
                & Q(import_vat_rate__gte=0) & Q(import_vat_rate__lte=100),
                name="shipment_rates_0_100",
            ),
        ]

    def __str__(self):
        return self.shipment_no or f"Shipment #{self.pk}"

    @property
    def cif_value(self):
        return money(self.goods_value + self.freight_cost + self.insurance_cost)

    @property
    def margin(self):
        return money(self.invoice_value - self.landed_cost)

    def calculate_costs(self):
        cif = self.cif_value
        self.customs_duty = money(cif * self.customs_duty_rate / 100)
        self.import_vat = money((cif + self.customs_duty) * self.import_vat_rate / 100)
        self.landed_cost = money(cif + self.customs_duty + self.import_vat + self.other_charges)

    def save(self, *args, **kwargs):
        self.calculate_costs()
        super().save(*args, **kwargs)
        if not self.shipment_no:
            self.shipment_no = f"DDP-{self.created_at:%Y}-{self.pk:06d}"
            super().save(update_fields=["shipment_no"])
