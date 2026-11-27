"""
Textile flow, step 6:  Planning → Cutting → Sewing → Finishing.

A production order (work order) makes one style of a confirmed order on one sewing line.
Capacity planning:
    daily target (pcs) = operators × working minutes × efficiency % ÷ SMV
    working days      = planned quantity ÷ daily target  (rounded up)
SMV = standard minute value: minutes one garment takes to sew.

Output is recorded as entries per stage. A stage can never get ahead of the one before it:
    Σ cut  ≤  planned × (1 + cut allowance)      (per size)
    Σ sewn good + sewing rejects  ≤  Σ cut
    Σ finished good + finishing rejects  ≤  Σ sewn good
The order completes when finished good pieces reach the planned quantity (or a manager closes it).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class ProductionLine(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="production_lines")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    operators = models.PositiveSmallIntegerField(default=30, help_text="Sewing machine operators")
    working_minutes = models.PositiveSmallIntegerField(default=480, help_text="Minutes per shift")
    efficiency_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("60"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["company", "code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_production_line_code"),
            models.CheckConstraint(condition=Q(efficiency_pct__gt=0) & Q(efficiency_pct__lte=100), name="line_efficiency_range"),
            models.CheckConstraint(condition=Q(operators__gt=0) & Q(working_minutes__gt=0), name="line_capacity_positive"),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def daily_target(self, smv):
        """Pieces per day for a garment of this SMV."""
        if not smv:
            return 0
        return int(Decimal(self.operators * self.working_minutes) * self.efficiency_pct / 100 / Decimal(smv))


class ProductionOrder(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In production"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="production_orders")
    wo_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    order = models.ForeignKey("merchandising.OrderConfirmation", on_delete=models.PROTECT, related_name="production_orders")
    order_line = models.ForeignKey("merchandising.OrderConfirmationLine", on_delete=models.PROTECT, related_name="production_orders")
    tech_pack = models.ForeignKey("development.TechPack", on_delete=models.SET_NULL, null=True, blank=True, related_name="production_orders")
    style_no = models.CharField(max_length=50, editable=False)
    colourway = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(help_text="Pieces to make")
    sizes = models.JSONField(default=dict, help_text='Pieces per size, e.g. {"4Y": 1000, "6Y": 1500}; adds up to quantity')
    line = models.ForeignKey(ProductionLine, on_delete=models.PROTECT, related_name="production_orders")
    smv = models.DecimalField("SMV (minutes)", max_digits=6, decimal_places=2)
    planned_start = models.DateField()
    planned_end = models.DateField()
    cut_allowance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("3"),
                                            help_text="Extra pieces that may be cut for rejects")
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED, editable=False, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    close_reason = models.TextField(blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["planned_start", "id"]
        indexes = [models.Index(fields=["line", "planned_start"])]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0) & Q(smv__gt=0), name="wo_quantity_smv_positive"),
            models.CheckConstraint(condition=Q(planned_end__gte=models.F("planned_start")), name="wo_end_after_start"),
            models.CheckConstraint(condition=Q(cut_allowance_pct__gte=0) & Q(cut_allowance_pct__lte=20), name="wo_cut_allowance_range"),
        ]

    def __str__(self):
        return self.wo_no or f"Work order #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.wo_no:
            self.wo_no = f"WO-{self.planned_start:%Y}-{self.pk:06d}"
            super().save(update_fields=["wo_no"])


class ProductionEntry(models.Model):
    """Output of one stage on one day. Never edited; a manager may delete the latest if it was wrong."""

    class Stage(models.TextChoices):
        CUTTING = "cutting", "Cutting"
        SEWING = "sewing", "Sewing"
        FINISHING = "finishing", "Finishing"

    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name="entries")
    stage = models.CharField(max_length=10, choices=Stage.choices, db_index=True)
    date = models.DateField(db_index=True)
    sizes = models.JSONField(default=dict, blank=True, help_text="Cutting: pieces per size")
    quantity = models.PositiveIntegerField(help_text="Good pieces")
    rejected = models.PositiveIntegerField(default=0, help_text="Pieces rejected at this stage")
    line = models.ForeignKey(ProductionLine, on_delete=models.PROTECT, null=True, blank=True, related_name="entries")
    lay_no = models.CharField("Lay / bundle no.", max_length=40, blank=True)
    fabric_used = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Cutting: fabric used")
    remarks = models.CharField(max_length=300, blank=True)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "production entries"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0) | Q(rejected__gt=0), name="entry_not_empty"),
            models.CheckConstraint(condition=Q(fabric_used__isnull=True) | Q(fabric_used__gte=0), name="entry_fabric_non_negative"),
        ]


class ActivityLog(models.Model):
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name="logs")
    action = models.CharField(max_length=40)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
