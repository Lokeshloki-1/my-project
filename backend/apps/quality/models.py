"""
Textile flow, step 7:  Inline QC → Final Inspection → Defect Control.

Inline QC (on the sewing line):
    DHU (defects per hundred units) = defects found ÷ pieces checked × 100
    green ≤ 2.5 · amber ≤ 5 · red > 5   — a red check opens a corrective action.

Final inspection (AQL, see aql.py): a sample is drawn from the finished lot; the lot passes when
    critical ≤ 0, major ≤ accept(major AQL), minor ≤ accept(minor AQL) and every checklist item is OK.
A failed lot opens a corrective action and can be re-inspected (round 2…).
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Severity(models.TextChoices):
    MINOR = "minor", "Minor"
    MAJOR = "major", "Major"
    CRITICAL = "critical", "Critical"


class DefectType(models.Model):
    class Category(models.TextChoices):
        SEWING = "sewing", "Sewing"
        FABRIC = "fabric", "Fabric"
        MEASUREMENT = "measurement", "Measurement"
        FINISHING = "finishing", "Finishing / pressing"
        PRINT = "print", "Print / embroidery"
        TRIMS = "trims", "Trims / labels"
        PACKING = "packing", "Packing"
        OTHER = "other", "Other"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="defect_types")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MAJOR, help_text="Default severity")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "code"]
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_defect_code")]

    def __str__(self):
        return f"{self.code} {self.name}"


class InlineInspection(models.Model):
    class Result(models.TextChoices):
        GREEN = "green", "Green"
        AMBER = "amber", "Amber"
        RED = "red", "Red"

    GREEN_MAX_DHU = 2.5
    AMBER_MAX_DHU = 5.0

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="inline_inspections")
    production_order = models.ForeignKey("production.ProductionOrder", on_delete=models.PROTECT, related_name="inline_inspections")
    line = models.ForeignKey("production.ProductionLine", on_delete=models.PROTECT, related_name="inline_inspections")
    date = models.DateField(db_index=True)
    operation = models.CharField(max_length=100, blank=True, help_text="e.g. Side seam, Neck rib attach")
    operator = models.CharField(max_length=100, blank=True, help_text="Operator name or number")
    pieces_checked = models.PositiveIntegerField()
    defective_pieces = models.PositiveIntegerField(help_text="Pieces with at least one defect")
    total_defects = models.PositiveIntegerField(default=0, editable=False)
    dhu = models.DecimalField("DHU", max_digits=7, decimal_places=2, default=0, editable=False)
    result = models.CharField(max_length=10, choices=Result.choices, editable=False, db_index=True)
    action_taken = models.TextField(blank=True, help_text="Required for a red result")
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["line", "date"])]
        constraints = [
            models.CheckConstraint(condition=Q(pieces_checked__gt=0), name="inline_pieces_positive"),
            models.CheckConstraint(condition=Q(defective_pieces__lte=F("pieces_checked")), name="inline_defective_within_checked"),
            models.CheckConstraint(condition=Q(defective_pieces__lte=F("total_defects")), name="inline_defective_within_defects"),
        ]


class InlineDefect(models.Model):
    inspection = models.ForeignKey(InlineInspection, on_delete=models.CASCADE, related_name="defects")
    defect_type = models.ForeignKey(DefectType, on_delete=models.PROTECT, related_name="inline_defects")
    count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inspection", "defect_type"], name="uniq_inline_defect"),
            models.CheckConstraint(condition=Q(count__gt=0), name="inline_defect_count_positive"),
        ]


class FinalInspection(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    CHECKLIST = [
        ("quantity", "Quantity and size ratio match the PO"),
        ("measurements", "Measurements within tolerance"),
        ("shade", "Shade matches the approved sample"),
        ("labels", "Labels, care labels and hang tags correct"),
        ("packing", "Folding and packing as instructed"),
        ("cartons", "Carton marks and dimensions correct"),
    ]

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="final_inspections")
    fi_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    production_order = models.ForeignKey("production.ProductionOrder", on_delete=models.PROTECT, related_name="final_inspections")
    round = models.PositiveSmallIntegerField(default=1, editable=False)
    previous = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="reinspection")
    inspection_date = models.DateField()
    inspected_by_party = models.CharField(max_length=100, blank=True, help_text="Own QA, buyer QA or third party (e.g. SGS)")
    lot_size = models.PositiveIntegerField(help_text="Finished pieces offered")
    aql_major = models.CharField(max_length=4, default="2.5")
    aql_minor = models.CharField(max_length=4, default="4.0")
    # Plan (set from the AQL table)
    code_letter = models.CharField(max_length=2, editable=False)
    sample_size = models.PositiveIntegerField(editable=False)
    accept_major = models.PositiveIntegerField(editable=False)
    accept_minor = models.PositiveIntegerField(editable=False)
    # Findings
    critical_found = models.PositiveIntegerField(default=0, editable=False)
    major_found = models.PositiveIntegerField(default=0, editable=False)
    minor_found = models.PositiveIntegerField(default=0, editable=False)
    checklist = models.JSONField(default=dict, blank=True, help_text="Checklist item → true (OK) / false (not OK)")
    cartons_checked = models.PositiveIntegerField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    fail_reasons = models.JSONField(default=list, blank=True, editable=False)
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inspection_date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(lot_size__gte=2), name="fi_lot_size_min"),
            models.CheckConstraint(condition=Q(sample_size__lte=F("lot_size")), name="fi_sample_within_lot"),
        ]

    def __str__(self):
        return self.fi_no or f"Final inspection #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.fi_no:
            self.fi_no = f"FI-{self.inspection_date:%Y}-{self.pk:06d}"
            super().save(update_fields=["fi_no"])


class FinalDefect(models.Model):
    inspection = models.ForeignKey(FinalInspection, on_delete=models.CASCADE, related_name="defects")
    defect_type = models.ForeignKey(DefectType, on_delete=models.PROTECT, related_name="final_defects")
    severity = models.CharField(max_length=10, choices=Severity.choices)
    count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inspection", "defect_type", "severity"], name="uniq_final_defect"),
            models.CheckConstraint(condition=Q(count__gt=0), name="final_defect_count_positive"),
        ]


class CorrectiveAction(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class Source(models.TextChoices):
        INLINE = "inline", "Inline QC"
        FINAL = "final", "Final inspection"
        OTHER = "other", "Other"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="corrective_actions")
    source = models.CharField(max_length=10, choices=Source.choices)
    inline_inspection = models.OneToOneField(InlineInspection, on_delete=models.PROTECT, null=True, blank=True, related_name="corrective_action")
    final_inspection = models.OneToOneField(FinalInspection, on_delete=models.PROTECT, null=True, blank=True, related_name="corrective_action")
    production_order = models.ForeignKey("production.ProductionOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="corrective_actions")
    problem = models.TextField()
    root_cause = models.TextField(blank=True)
    action = models.TextField(blank=True, help_text="What was done so it doesn't happen again")
    owner = models.CharField(max_length=100, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, editable=False, db_index=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(status="open") | (~Q(root_cause="") & ~Q(action="")), name="closed_capa_has_cause_and_action"),
        ]
