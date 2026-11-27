"""
Textile flow, step 4:  Material Requirement → RFQ → Supplier PO.

Material requirement (from a confirmed order):
    required qty = Σ over styles (order pcs × BOM consumption per piece) × (1 + wastage % / 100)
using the latest released tech pack of each style. Identical materials across styles are merged.

RFQ: the materials are sent to several suppliers; each supplier's prices are recorded and compared;
one supplier is awarded and a draft supplier PO is created from their quote.

Supplier PO: draft → approved (manager) → sent to the supplier; cancelled frees the quantity.
"Ordered" on a requirement line = Σ quantities on PO lines that are not cancelled.
Receiving the goods is the next module (Inventory: goods receipt).
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.development.models import BOMItem

TWO = Decimal("0.01")


def dec(value):
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def q2(value):
    return dec(value).quantize(TWO, ROUND_HALF_UP)


def ceil2(value):
    return dec(value).quantize(TWO, ROUND_CEILING)


def _number(prefix, when, pk):
    return f"{prefix}-{when:%Y}-{pk:06d}"


class Supplier(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="suppliers")
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India")
    address = models.TextField(blank=True)
    tax_id = models.CharField("GSTIN / Tax ID", max_length=30, blank=True)
    categories = models.JSONField(default=list, blank=True, help_text="Material types they supply (BOM categories)")
    payment_terms = models.CharField(max_length=100, blank=True, help_text="e.g. 30 days credit")
    lead_time_days = models.PositiveSmallIntegerField(default=14)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="uniq_supplier_name_per_company")]

    def __str__(self):
        return self.name


class MaterialRequirement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="material_requirements")
    mr_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    order = models.OneToOneField(
        "merchandising.OrderConfirmation", on_delete=models.PROTECT, null=True, blank=True, related_name="material_requirement"
    )
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    title = models.CharField(max_length=200)
    needed_by = models.DateField(null=True, blank=True, help_text="Materials must be in the factory by this date")
    wastage_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("5"))
    notes = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True, editable=False, help_text="Problems found while calculating")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(wastage_pct__gte=0) & Q(wastage_pct__lte=100), name="mr_wastage_0_100"),
        ]

    def __str__(self):
        return self.mr_no or f"Requirement #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.mr_no:
            self.mr_no = _number("MR", self.created_at, self.pk)
            super().save(update_fields=["mr_no"])


class RequirementLine(models.Model):
    requirement = models.ForeignKey(MaterialRequirement, on_delete=models.CASCADE, related_name="lines")
    category = models.CharField(max_length=20, choices=BOMItem.Category.choices)
    description = models.CharField(max_length=200)
    colour = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=20, default="pc")
    supplier_hint = models.CharField(max_length=150, blank=True, help_text="Supplier named in the tech pack")
    styles = models.CharField(max_length=200, blank=True, help_text="Styles that use this material")
    net_qty = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Before wastage")
    required_qty = models.DecimalField(max_digits=14, decimal_places=2)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(required_qty__gte=0) & Q(net_qty__gte=0), name="req_line_qty_non_negative"),
        ]

    def __str__(self):
        return self.description


class RFQ(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent to suppliers"
        AWARDED = "awarded", "Awarded"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="rfqs")
    rfq_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    requirement = models.ForeignKey(MaterialRequirement, on_delete=models.PROTECT, null=True, blank=True, related_name="rfqs")
    title = models.CharField(max_length=200)
    reply_by = models.DateField(help_text="Suppliers must quote by this date")
    required_by = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    notes = models.TextField(blank=True, help_text="Terms sent to suppliers")
    suppliers = models.ManyToManyField(Supplier, related_name="rfqs", blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    awarded_supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="awarded_rfqs"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "RFQ"

    def __str__(self):
        return self.rfq_no or f"RFQ #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.rfq_no:
            self.rfq_no = _number("RFQ", self.created_at, self.pk)
            super().save(update_fields=["rfq_no"])


class RFQLine(models.Model):
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="lines")
    requirement_line = models.ForeignKey(RequirementLine, on_delete=models.PROTECT, null=True, blank=True, related_name="rfq_lines")
    category = models.CharField(max_length=20, choices=BOMItem.Category.choices, default=BOMItem.Category.FABRIC)
    description = models.CharField(max_length=200)
    colour = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=20, default="pc")
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="rfq_line_qty_positive")]


class SupplierQuote(models.Model):
    """A supplier's answer to an RFQ."""

    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="quotes")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="quotes")
    currency = models.CharField(max_length=3, default="INR")
    valid_until = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    complete = models.BooleanField(default=False, editable=False, help_text="Priced every RFQ line")
    received_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["total", "id"]
        constraints = [models.UniqueConstraint(fields=["rfq", "supplier"], name="one_quote_per_supplier_per_rfq")]


class SupplierQuoteLine(models.Model):
    quote = models.ForeignKey(SupplierQuote, on_delete=models.CASCADE, related_name="lines")
    rfq_line = models.ForeignKey(RFQLine, on_delete=models.CASCADE, related_name="quote_lines")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    lead_time_days = models.PositiveSmallIntegerField(null=True, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["quote", "rfq_line"], name="one_price_per_rfq_line"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="quote_price_non_negative"),
        ]

    def save(self, *args, **kwargs):
        self.amount = q2(self.rfq_line.quantity * dec(self.unit_price))
        super().save(*args, **kwargs)


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent to supplier"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="purchase_orders")
    po_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    requirement = models.ForeignKey(MaterialRequirement, on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_orders")
    rfq = models.ForeignKey(RFQ, on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_orders")
    order_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    payment_terms = models.CharField(max_length=100, blank=True)
    delivery_address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancel_reason = models.TextField(blank=True, editable=False)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-order_date", "-id"]
        indexes = [models.Index(fields=["supplier", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(delivery_date__isnull=True) | Q(delivery_date__gte=models.F("order_date")),
                name="po_delivery_after_order_date",
            ),
        ]

    def __str__(self):
        return self.po_no or f"PO #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.po_no:
            self.po_no = _number("PO", self.order_date, self.pk)
            super().save(update_fields=["po_no"])

    def recalculate(self):
        self.total = q2(sum((line.amount for line in self.lines.all()), Decimal("0")))
        self.save(update_fields=["total", "updated_at"])


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    requirement_line = models.ForeignKey(RequirementLine, on_delete=models.PROTECT, null=True, blank=True, related_name="po_lines")
    category = models.CharField(max_length=20, choices=BOMItem.Category.choices, default=BOMItem.Category.FABRIC)
    description = models.CharField(max_length=200)
    colour = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=20, default="pc")
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0) & Q(unit_price__gte=0), name="po_line_positive"),
        ]

    def save(self, *args, **kwargs):
        self.amount = q2(dec(self.quantity) * dec(self.unit_price))
        super().save(*args, **kwargs)


class ActivityLog(models.Model):
    class DocType(models.TextChoices):
        REQUIREMENT = "requirement", "Material requirement"
        RFQ = "rfq", "RFQ"
        PO = "po", "Purchase order"

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    doc_id = models.PositiveIntegerField()
    action = models.CharField(max_length=40)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]
