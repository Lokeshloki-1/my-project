"""
Textile flow, step 3:  Tech Pack → Sampling → Approval.

A tech pack describes one style for one buyer: spec, measurement chart (points of measure with a
tolerance and a value per size) and bill of materials. It is released before samples are made;
changing a released tech pack means making a new revision.

Samples are made from a released tech pack and go through rounds:
    requested → in_progress → ready → sent → approved | approved_with_comments | rejected
Each sample can record the measured value of every point of measure for one size; the server
checks each against spec ± tolerance. When a PP (pre-production) sample is approved, the tech pack
is approved for production.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.buyers.models import BuyerRequirement


def _number(prefix, when, pk):
    return f"{prefix}-{when:%Y}-{pk:06d}"


class TechPack(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RELEASED = "released", "Released"
        SUPERSEDED = "superseded", "Superseded"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="tech_packs")
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="tech_packs")
    tp_no = models.CharField(max_length=30, null=True, blank=True, editable=False)
    revision = models.PositiveSmallIntegerField(default=1, editable=False)
    previous = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="next_revision"
    )
    style_no = models.CharField(max_length=50)
    style_name = models.CharField(max_length=200)
    season = models.CharField(max_length=20, blank=True, help_text="e.g. SS27, AW27")
    category = models.CharField(max_length=20, choices=BuyerRequirement.Category.choices, default=BuyerRequirement.Category.KNITS)
    description = models.TextField(blank=True)
    fabric_composition = models.CharField(max_length=200, blank=True)
    gsm = models.PositiveIntegerField(null=True, blank=True)
    colourways = models.JSONField(default=list, blank=True, help_text='e.g. ["Navy", "White / Red stripe"]')
    sizes = models.JSONField(default=list, blank=True, help_text='Size columns of the measurement chart, e.g. ["S", "M", "L"]')
    base_size = models.CharField(max_length=20, blank=True, help_text="Size samples are usually made in")
    construction = models.TextField(blank=True, help_text="Seams, stitching, finishing details")
    wash_care = models.TextField(blank=True, help_text="Care label / wash instructions")
    packing = models.TextField(blank=True)
    cost_sheet = models.ForeignKey(
        "merchandising.CostSheet", on_delete=models.SET_NULL, null=True, blank=True, related_name="tech_packs"
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+"
    )
    released_at = models.DateTimeField(null=True, blank=True, editable=False)
    production_approved = models.BooleanField(default=False, editable=False)
    production_approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tp_no", "revision"], name="tech_pack_number_revision_unique"),
        ]

    def __str__(self):
        return f"{self.tp_no or 'Tech pack'} rev {self.revision} - {self.style_no}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.tp_no:
            # A revision keeps the number of the first version.
            self.tp_no = self.previous.tp_no if self.previous_id else _number("TP", self.created_at, self.pk)
            super().save(update_fields=["tp_no"])


class Measurement(models.Model):
    """One point of measure (POM) on the size chart."""

    tech_pack = models.ForeignKey(TechPack, on_delete=models.CASCADE, related_name="measurements")
    code = models.CharField(max_length=10, blank=True, help_text="e.g. A, B, HPS-1")
    point = models.CharField("Point of measure", max_length=150, help_text="e.g. Chest width, 2.5 cm below armhole")
    tolerance = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("1.00"), help_text="± in cm")
    values = models.JSONField(default=dict, help_text='Spec per size in cm, e.g. {"S": 48, "M": 50}')
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.CheckConstraint(condition=Q(tolerance__gte=0), name="measurement_tolerance_non_negative")]

    def __str__(self):
        return self.point


class BOMItem(models.Model):
    class Category(models.TextChoices):
        FABRIC = "fabric", "Fabric"
        TRIM = "trim", "Trim"
        LABEL = "label", "Label"
        THREAD = "thread", "Thread"
        PRINT = "print", "Print / embroidery"
        PACKAGING = "packaging", "Packaging"
        OTHER = "other", "Other"

    tech_pack = models.ForeignKey(TechPack, on_delete=models.CASCADE, related_name="bom")
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=200)
    supplier = models.CharField(max_length=150, blank=True)
    colour = models.CharField(max_length=100, blank=True)
    placement = models.CharField(max_length=150, blank=True, help_text="Where it goes on the garment")
    consumption = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, help_text="Per piece")
    unit = models.CharField(max_length=20, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(consumption__isnull=True) | Q(consumption__gte=0), name="bom_consumption_non_negative"),
        ]

    def __str__(self):
        return self.description


class Sample(models.Model):
    class Type(models.TextChoices):
        PROTO = "proto", "Proto sample"
        FIT = "fit", "Fit sample"
        SIZE_SET = "size_set", "Size set"
        SALESMAN = "salesman", "Salesman sample"
        PHOTO = "photo", "Photo sample"
        PP = "pp", "PP (pre-production) sample"
        TOP = "top", "TOP (top of production) sample"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        IN_PROGRESS = "in_progress", "In progress"
        READY = "ready", "Ready"
        SENT = "sent", "Sent to buyer"
        APPROVED = "approved", "Approved"
        APPROVED_WITH_COMMENTS = "approved_with_comments", "Approved with comments"
        REJECTED = "rejected", "Rejected"

    OPEN_STATUSES = [Status.REQUESTED, Status.IN_PROGRESS, Status.READY, Status.SENT]
    APPROVED_STATUSES = [Status.APPROVED, Status.APPROVED_WITH_COMMENTS]

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="samples")
    tech_pack = models.ForeignKey(TechPack, on_delete=models.PROTECT, related_name="samples")
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="samples")
    sample_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    sample_type = models.CharField(max_length=20, choices=Type.choices)
    round = models.PositiveSmallIntegerField(default=1, editable=False, help_text="1 for the first sample of this type, 2 for the resubmission…")
    previous = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="resubmission"
    )
    colourway = models.CharField(max_length=100, blank=True)
    size = models.CharField(max_length=20, blank=True, help_text="Size that is measured")
    quantity = models.PositiveSmallIntegerField(default=1)
    requested_on = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    instructions = models.TextField(blank=True, help_text="What to check or change in this round")

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUESTED, editable=False, db_index=True)
    courier = models.CharField(max_length=60, blank=True, editable=False)
    tracking_no = models.CharField(max_length=100, blank=True, editable=False)
    sent_on = models.DateField(null=True, blank=True, editable=False)
    buyer_comments = models.TextField(blank=True, editable=False)
    decided_on = models.DateField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tech_pack", "sample_type"])]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sample_quantity_positive"),
            models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(buyer_comments=""), name="rejected_sample_has_comments"
            ),
        ]

    def __str__(self):
        return self.sample_no or f"Sample #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.sample_no:
            self.sample_no = _number("SMP", self.created_at, self.pk)
            super().save(update_fields=["sample_no"])


class SampleMeasurement(models.Model):
    """Measured value of one point of measure on a sample, checked against spec ± tolerance."""

    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="measurements")
    measurement = models.ForeignKey(Measurement, on_delete=models.CASCADE, related_name="+")
    spec = models.DecimalField(max_digits=8, decimal_places=2, editable=False)
    tolerance = models.DecimalField(max_digits=6, decimal_places=2, editable=False)
    actual = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["measurement__position", "measurement_id"]
        constraints = [models.UniqueConstraint(fields=["sample", "measurement"], name="one_reading_per_point")]

    @property
    def deviation(self):
        return self.actual - self.spec

    @property
    def within_tolerance(self):
        return abs(self.deviation) <= self.tolerance


class ActivityLog(models.Model):
    class DocType(models.TextChoices):
        TECH_PACK = "tech_pack", "Tech pack"
        SAMPLE = "sample", "Sample"

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    doc_id = models.PositiveIntegerField()
    action = models.CharField(max_length=40)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]
