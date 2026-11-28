"""
Textile flow, step 5:  Goods Receipt → Inspection → Stock Allocation  (raw materials).

    Supplier PO (sent) ──▶ GRN draft ──submit──▶ received (awaiting inspection)
                                       ──inspect──▶ inspected: accepted qty goes into stock, rejected goes back

Material stock per warehouse:
    on_hand    physical quantity (changed only by MaterialMovement rows)
    allocated  reserved for orders (≤ on_hand)
    available  = on_hand − allocated

Allocation reserves stock for an order's material requirement; issuing it to production takes it out
of stock. Every stock change is a MaterialMovement — a permanent ledger that is never edited.
The database refuses negative stock and allocation above stock even if the app has a bug.
Finished-goods stock (sales products) stays in apps.inventory; warehouses are shared.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.development.models import BOMItem


def _number(prefix, when, pk):
    return f"{prefix}-{when:%Y}-{pk:06d}"


class Material(models.Model):
    """A raw material kept in stock, e.g. “180 GSM organic cotton, Navy, kg”."""

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="materials")
    code = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    category = models.CharField(max_length=20, choices=BOMItem.Category.choices)
    description = models.CharField(max_length=200)
    colour = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=20)
    reorder_level = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "description", "colour"]
        constraints = [
            models.UniqueConstraint(fields=["company", "category", "description", "colour", "unit"], name="uniq_material"),
            models.CheckConstraint(condition=Q(reorder_level__gte=0), name="material_reorder_non_negative"),
        ]

    def __str__(self):
        return " · ".join(x for x in (self.description, self.colour, self.unit) if x)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f"MAT-{self.pk:06d}"
            super().save(update_fields=["code"])


class MaterialStock(models.Model):
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="stock")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="material_stock")
    on_hand = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    allocated = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    value = models.DecimalField(max_digits=16, decimal_places=2, default=0, help_text="On hand × average cost")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["material__category", "material__description", "warehouse__name"]
        constraints = [
            models.UniqueConstraint(fields=["material", "warehouse"], name="uniq_material_stock"),
            models.CheckConstraint(condition=Q(on_hand__gte=0), name="material_on_hand_non_negative"),
            models.CheckConstraint(condition=Q(allocated__gte=0) & Q(allocated__lte=F("on_hand")), name="allocated_within_on_hand"),
            models.CheckConstraint(condition=Q(value__gte=0), name="material_value_non_negative"),
        ]

    @property
    def available(self):
        return self.on_hand - self.allocated

    @property
    def average_cost(self):
        return (self.value / self.on_hand).quantize(Decimal("0.01")) if self.on_hand else Decimal("0")


class MaterialMovement(models.Model):
    class Type(models.TextChoices):
        RECEIPT = "receipt", "Receipt (GRN)"
        ISSUE = "issue", "Issue to production"
        ADJUSTMENT = "adjustment", "Adjustment (stock count)"

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="movements")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="material_movements")
    movement_type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=2, help_text="Positive = in, negative = out")
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    grn_line = models.ForeignKey("GoodsReceiptLine", on_delete=models.PROTECT, null=True, blank=True, related_name="movements")
    allocation = models.ForeignKey("MaterialAllocation", on_delete=models.PROTECT, null=True, blank=True, related_name="movements")
    reference = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["material", "warehouse", "created_at"])]
        constraints = [
            models.CheckConstraint(condition=~Q(quantity=0), name="material_movement_non_zero"),
            models.CheckConstraint(condition=Q(balance_after__gte=0), name="material_movement_balance_non_negative"),
        ]


class GoodsReceipt(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RECEIVED = "received", "Awaiting inspection"
        INSPECTED = "inspected", "Inspected"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="goods_receipts")
    grn_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    purchase_order = models.ForeignKey("procurement.PurchaseOrder", on_delete=models.PROTECT, related_name="goods_receipts")
    supplier = models.ForeignKey("procurement.Supplier", on_delete=models.PROTECT, related_name="goods_receipts", editable=False)
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="goods_receipts")
    received_on = models.DateField()
    challan_no = models.CharField("Supplier delivery challan no.", max_length=60, blank=True)
    invoice_no = models.CharField("Supplier invoice no.", max_length=60, blank=True)
    vehicle_no = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+")
    inspected_at = models.DateTimeField(null=True, blank=True, editable=False)
    inspection_notes = models.TextField(blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        verbose_name = "goods receipt"

    def __str__(self):
        return self.grn_no or f"GRN #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.grn_no:
            self.grn_no = _number("GRN", self.received_on, self.pk)
            super().save(update_fields=["grn_no"])


class GoodsReceiptLine(models.Model):
    class Result(models.TextChoices):
        PENDING = "pending", "Not inspected"
        PASSED = "passed", "Passed"
        PARTIAL = "partial", "Partly rejected"
        FAILED = "failed", "Rejected"

    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    po_line = models.ForeignKey("procurement.PurchaseOrderLine", on_delete=models.PROTECT, related_name="grn_lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="grn_lines", editable=False)
    received_qty = models.DecimalField(max_digits=14, decimal_places=2)
    lot_no = models.CharField("Lot / dye lot", max_length=60, blank=True)
    rolls = models.PositiveIntegerField(null=True, blank=True, help_text="Rolls, bales or cartons")
    accepted_qty = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    rejected_qty = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    result = models.CharField(max_length=10, choices=Result.choices, default=Result.PENDING, editable=False)
    remarks = models.CharField(max_length=300, blank=True, editable=False, help_text="Inspection findings")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(received_qty__gt=0), name="grn_received_positive"),
            models.CheckConstraint(condition=Q(accepted_qty__gte=0) & Q(rejected_qty__gte=0), name="grn_inspected_non_negative"),
            models.CheckConstraint(
                condition=Q(result="pending") | Q(received_qty=F("accepted_qty") + F("rejected_qty")),
                name="grn_inspected_adds_up",
            ),
        ]


class MaterialAllocation(models.Model):
    """Stock reserved for an order; issued to production in one or more steps."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Allocated"
        ISSUED = "issued", "Issued"
        RELEASED = "released", "Released"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="material_allocations")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="allocations")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="material_allocations")
    order = models.ForeignKey("merchandising.OrderConfirmation", on_delete=models.PROTECT, related_name="material_allocations")
    requirement_line = models.ForeignKey(
        "procurement.RequirementLine", on_delete=models.PROTECT, null=True, blank=True, related_name="allocations"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    issued_qty = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    released_qty = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, editable=False, db_index=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="allocation_positive"),
            models.CheckConstraint(
                condition=Q(issued_qty__gte=0) & Q(released_qty__gte=0) & Q(quantity__gte=F("issued_qty") + F("released_qty")),
                name="allocation_issued_within_quantity",
            ),
        ]

    @property
    def remaining(self):
        return self.quantity - self.issued_qty - self.released_qty


class ActivityLog(models.Model):
    class DocType(models.TextChoices):
        GRN = "grn", "Goods receipt"
        ALLOCATION = "allocation", "Allocation"

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    doc_id = models.PositiveIntegerField()
    action = models.CharField(max_length=40)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]
