"""
Textile flow, step 2:  Costing → Quotation → Order Confirmation.

Cost sheet (per style, per piece, in the buyer's currency):

    line amount     = consumption × rate × (1 + wastage % / 100)
    direct cost     = Σ line amounts
    overhead        = direct cost × overhead %
    total cost      = direct cost + overhead
    margin          = total cost × margin %
    net price       = total cost + margin
    FOB price       = net price ÷ (1 − commission % / 100)     (agent commission is a share of the price)
    commission      = FOB price − net price

A manager approves the cost sheet; only approved cost sheets can be quoted.
A quotation is for an approved buyer. When the buyer accepts it, an order confirmation is
created from it; confirming the order checks the buyer's credit limit.
All totals are calculated on the server — never sent by the client.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.buyers.models import BuyerRequirement, CreditCheck

FOUR = Decimal("0.0001")
TWO = Decimal("0.01")


def dec(value):
    """Decimal from whatever a form or default gave us (int, str, float, Decimal)."""
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def q4(value):
    return Decimal(value).quantize(FOUR, ROUND_HALF_UP)


def q2(value):
    return Decimal(value).quantize(TWO, ROUND_HALF_UP)


def _number(prefix, when, pk):
    return f"{prefix}-{when:%Y}-{pk:06d}"


class CostSheet(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="cost_sheets")
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="cost_sheets")
    cost_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    style_no = models.CharField(max_length=50)
    style_name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=BuyerRequirement.Category.choices, default=BuyerRequirement.Category.KNITS)
    fabric_composition = models.CharField(max_length=200, blank=True)
    gsm = models.PositiveIntegerField(null=True, blank=True)
    size_range = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=0, help_text="Pieces the costing is based on")
    currency = models.CharField(max_length=3, default="USD")
    overhead_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10"))
    margin_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("12"))
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Buying agent commission")
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)

    # Calculated per piece by recalculate().
    direct_cost = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)
    overhead_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)
    total_cost = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)
    margin_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)
    commission_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)
    fob_price = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(overhead_pct__gte=0) & Q(overhead_pct__lte=100) & Q(margin_pct__gte=0) & Q(margin_pct__lte=100)
                & Q(commission_pct__gte=0) & Q(commission_pct__lt=50),
                name="cost_sheet_percents_in_range",
            ),
        ]

    def __str__(self):
        return f"{self.cost_no or 'Cost sheet'} - {self.style_no}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.cost_no:
            self.cost_no = _number("CS", self.created_at, self.pk)
            super().save(update_fields=["cost_no"])

    def recalculate(self):
        direct = sum((line.amount for line in self.lines.all()), Decimal("0"))
        self.direct_cost = q4(direct)
        overhead_pct, margin_pct, commission_pct = dec(self.overhead_pct), dec(self.margin_pct), dec(self.commission_pct)
        self.overhead_amount = q4(direct * overhead_pct / 100)
        self.total_cost = self.direct_cost + self.overhead_amount
        self.margin_amount = q4(self.total_cost * margin_pct / 100)
        net = self.total_cost + self.margin_amount
        fob = net / (1 - commission_pct / 100)
        self.fob_price = q2(fob)
        self.commission_amount = q4(fob - net)
        self.save(update_fields=[
            "direct_cost", "overhead_amount", "total_cost", "margin_amount", "commission_amount", "fob_price", "updated_at",
        ])


class CostSheetLine(models.Model):
    class Category(models.TextChoices):
        FABRIC = "fabric", "Fabric"
        TRIMS = "trims", "Trims"
        ACCESSORIES = "accessories", "Accessories"
        PRINT_EMBROIDERY = "print_embroidery", "Print / embroidery"
        WASHING = "washing", "Washing / dyeing"
        CMT = "cmt", "CMT (cut, make, trim)"
        TESTING = "testing", "Testing"
        PACKING = "packing", "Packing"
        FREIGHT = "freight", "Freight / logistics"
        OTHER = "other", "Other"

    cost_sheet = models.ForeignKey(CostSheet, on_delete=models.CASCADE, related_name="lines")
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, default="pc", help_text="kg, m, pc, dozen, …")
    consumption = models.DecimalField(max_digits=12, decimal_places=4, help_text="Per piece")
    rate = models.DecimalField(max_digits=12, decimal_places=4, help_text="Per unit, in the cost sheet currency")
    wastage_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(consumption__gte=0) & Q(rate__gte=0) & Q(wastage_pct__gte=0) & Q(wastage_pct__lte=100),
                name="cost_line_values_in_range",
            ),
        ]

    def save(self, *args, **kwargs):
        self.amount = q4(dec(self.consumption) * dec(self.rate) * (1 + dec(self.wastage_pct) / 100))
        super().save(*args, **kwargs)


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent to buyer"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="quotations")
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="quotations")
    quote_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    quote_date = models.DateField()
    valid_until = models.DateField()
    currency = models.CharField(max_length=3, default="USD")
    incoterm = models.CharField(max_length=3, choices=[(c, c) for c in ("EXW", "FOB", "CIF", "DDP")], default="FOB")
    delivery_port = models.CharField(max_length=100, blank=True)
    payment_terms = models.CharField(max_length=20, choices=CreditCheck.PaymentTerms.choices, default=CreditCheck.PaymentTerms.LC_SIGHT)
    delivery_date = models.DateField(null=True, blank=True, help_text="Proposed ex-factory date")
    notes = models.TextField(blank=True, help_text="Terms printed on the quotation")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    reject_reason = models.TextField(blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    accepted_at = models.DateTimeField(null=True, blank=True, editable=False)
    total_quantity = models.PositiveIntegerField(default=0, editable=False)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-quote_date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(valid_until__gte=models.F("quote_date")), name="quote_validity_after_date"),
        ]

    def __str__(self):
        return self.quote_no or f"Quotation #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.quote_no:
            self.quote_no = _number("QT", self.quote_date, self.pk)
            super().save(update_fields=["quote_no"])

    def recalculate(self):
        lines = list(self.lines.all())
        self.total_quantity = sum(line.quantity for line in lines)
        self.total_amount = q2(sum((line.amount for line in lines), Decimal("0")))
        self.save(update_fields=["total_quantity", "total_amount", "updated_at"])


class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    cost_sheet = models.ForeignKey(CostSheet, on_delete=models.PROTECT, related_name="quotation_lines")
    style_no = models.CharField(max_length=50)
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0) & Q(unit_price__gte=0), name="quote_line_positive"),
        ]

    def save(self, *args, **kwargs):
        self.amount = q2(self.quantity * dec(self.unit_price))
        super().save(*args, **kwargs)


class OrderConfirmation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="order_confirmations")
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="order_confirmations")
    quotation = models.OneToOneField(Quotation, on_delete=models.PROTECT, related_name="order_confirmation")
    oc_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    buyer_po_no = models.CharField("Buyer PO number", max_length=60, blank=True)
    po_date = models.DateField(null=True, blank=True)
    ship_date = models.DateField(null=True, blank=True, help_text="Agreed ex-factory / shipment date")
    currency = models.CharField(max_length=3, editable=False)
    incoterm = models.CharField(max_length=3, editable=False)
    payment_terms = models.CharField(max_length=20, choices=CreditCheck.PaymentTerms.choices, editable=False)
    delivery_port = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    credit_override = models.BooleanField(default=False, editable=False)
    override_reason = models.TextField(blank=True, editable=False)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancel_reason = models.TextField(blank=True, editable=False)
    total_quantity = models.PositiveIntegerField(default=0, editable=False)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["buyer", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="confirmed") | (~Q(buyer_po_no="") & Q(ship_date__isnull=False)),
                name="confirmed_order_has_po_and_ship_date",
            ),
        ]

    def __str__(self):
        return self.oc_no or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.oc_no:
            self.oc_no = _number("OC", self.created_at, self.pk)
            super().save(update_fields=["oc_no"])

    def recalculate(self):
        lines = list(self.lines.all())
        self.total_quantity = sum(line.quantity for line in lines)
        self.total_amount = q2(sum((line.amount for line in lines), Decimal("0")))
        self.save(update_fields=["total_quantity", "total_amount", "updated_at"])


class OrderConfirmationLine(models.Model):
    order = models.ForeignKey(OrderConfirmation, on_delete=models.CASCADE, related_name="lines")
    cost_sheet = models.ForeignKey(CostSheet, on_delete=models.PROTECT, related_name="order_lines")
    style_no = models.CharField(max_length=50)
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0) & Q(unit_price__gte=0), name="oc_line_positive"),
        ]

    def save(self, *args, **kwargs):
        self.amount = q2(self.quantity * dec(self.unit_price))
        super().save(*args, **kwargs)


class ActivityLog(models.Model):
    """History of status changes on cost sheets, quotations and orders."""

    class DocType(models.TextChoices):
        COST_SHEET = "cost_sheet", "Cost sheet"
        QUOTATION = "quotation", "Quotation"
        ORDER = "order", "Order confirmation"

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    doc_id = models.PositiveIntegerField()
    action = models.CharField(max_length=30)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]

    def __str__(self):
        return f"{self.doc_type} {self.doc_id}: {self.action}"
