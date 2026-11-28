"""
Textile flow, step 8:  Packing List → Shipping → Export Documents.

Packing list (per confirmed order): carton ranges, each with pieces per size per carton.
    pcs per carton = Σ sizes · pcs = cartons × pcs per carton
    CBM per carton = L × W × H (cm) ÷ 1,000,000
Only pieces covered by a PASSED final inspection may be packed:
    packable for a work order = min(finished good, Σ passed inspection lots) − already packed (finalized lists)

Export shipment: planned → booked → shipped (on board) → delivered; cancelled before shipping.
Each shipment has a checklist of export documents; the commercial invoice and the packing list
are generated as PDFs.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q


def _number(prefix, when, pk):
    return f"{prefix}-{when:%Y}-{pk:06d}"


class PackingList(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        FINALIZED = "finalized", "Finalized"

    class Method(models.TextChoices):
        SOLID = "solid", "Solid size, solid colour"
        RATIO = "ratio", "Ratio pack (assorted sizes)"
        MIXED = "mixed", "Mixed"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="packing_lists")
    pl_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    order = models.ForeignKey("merchandising.OrderConfirmation", on_delete=models.PROTECT, related_name="packing_lists")
    shipment = models.ForeignKey("ExportShipment", on_delete=models.SET_NULL, null=True, blank=True, related_name="packing_lists")
    pack_date = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.SOLID)
    shipping_marks = models.TextField(blank=True, help_text="Printed on the cartons")
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="+")
    finalized_at = models.DateTimeField(null=True, blank=True, editable=False)
    total_cartons = models.PositiveIntegerField(default=0, editable=False)
    total_pcs = models.PositiveIntegerField(default=0, editable=False)
    net_weight = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    gross_weight = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    cbm = models.DecimalField(max_digits=10, decimal_places=3, default=0, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pack_date", "-id"]

    def __str__(self):
        return self.pl_no or f"Packing list #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.pl_no:
            self.pl_no = _number("PL", self.pack_date, self.pk)
            super().save(update_fields=["pl_no"])

    def recalculate(self):
        groups = list(self.groups.all())
        self.total_cartons = sum(g.cartons for g in groups)
        self.total_pcs = sum(g.total_pcs for g in groups)
        self.net_weight = sum((g.cartons * g.net_weight for g in groups), Decimal("0"))
        self.gross_weight = sum((g.cartons * g.gross_weight for g in groups), Decimal("0"))
        self.cbm = sum((g.cartons * g.cbm_per_carton for g in groups), Decimal("0")).quantize(Decimal("0.001"), ROUND_HALF_UP)
        self.save(update_fields=["total_cartons", "total_pcs", "net_weight", "gross_weight", "cbm", "updated_at"])


class CartonGroup(models.Model):
    """Cartons from_carton…to_carton, all packed the same way."""

    packing_list = models.ForeignKey(PackingList, on_delete=models.CASCADE, related_name="groups")
    production_order = models.ForeignKey("production.ProductionOrder", on_delete=models.PROTECT, related_name="carton_groups")
    style_no = models.CharField(max_length=50, editable=False)
    colourway = models.CharField(max_length=100, blank=True)
    from_carton = models.PositiveIntegerField()
    to_carton = models.PositiveIntegerField()
    sizes = models.JSONField(help_text='Pieces per size in ONE carton, e.g. {"6Y": 24}')
    net_weight = models.DecimalField(max_digits=8, decimal_places=2, help_text="kg per carton")
    gross_weight = models.DecimalField(max_digits=8, decimal_places=2, help_text="kg per carton")
    length_cm = models.DecimalField(max_digits=6, decimal_places=1)
    width_cm = models.DecimalField(max_digits=6, decimal_places=1)
    height_cm = models.DecimalField(max_digits=6, decimal_places=1)

    class Meta:
        ordering = ["from_carton"]
        constraints = [
            models.CheckConstraint(condition=Q(from_carton__gte=1) & Q(to_carton__gte=F("from_carton")), name="carton_range_valid"),
            models.CheckConstraint(condition=Q(gross_weight__gte=F("net_weight")) & Q(net_weight__gt=0), name="carton_weights_valid"),
            models.CheckConstraint(condition=Q(length_cm__gt=0) & Q(width_cm__gt=0) & Q(height_cm__gt=0), name="carton_dimensions_positive"),
        ]

    @property
    def cartons(self):
        return self.to_carton - self.from_carton + 1

    @property
    def pcs_per_carton(self):
        return sum(int(v) for v in self.sizes.values())

    @property
    def total_pcs(self):
        return self.cartons * self.pcs_per_carton

    @property
    def cbm_per_carton(self):
        return self.length_cm * self.width_cm * self.height_cm / Decimal("1000000")


class ExportShipment(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        BOOKED = "booked", "Booked"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class Mode(models.TextChoices):
        SEA = "sea", "Sea"
        AIR = "air", "Air"
        ROAD = "road", "Road"
        COURIER = "courier", "Courier"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="export_shipments")
    shipment_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    order = models.ForeignKey("merchandising.OrderConfirmation", on_delete=models.PROTECT, related_name="export_shipments")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SEA)
    port_of_loading = models.CharField(max_length=100, default="Chennai, India")
    port_of_discharge = models.CharField(max_length=100, blank=True)
    final_destination = models.CharField(max_length=100, blank=True)
    forwarder = models.CharField(max_length=150, blank=True)
    carrier = models.CharField(max_length=100, blank=True, help_text="Shipping line or airline")
    vessel = models.CharField("Vessel / flight", max_length=100, blank=True)
    voyage = models.CharField("Voyage no.", max_length=50, blank=True)
    container_type = models.CharField(max_length=10, blank=True, help_text="20GP, 40GP, 40HC, LCL")
    container_no = models.CharField(max_length=20, blank=True)
    seal_no = models.CharField(max_length=30, blank=True)
    etd = models.DateField("ETD", null=True, blank=True)
    eta = models.DateField("ETA", null=True, blank=True)
    on_board_date = models.DateField(null=True, blank=True, editable=False)
    delivered_date = models.DateField(null=True, blank=True, editable=False)
    bl_no = models.CharField("B/L or AWB no.", max_length=50, blank=True)
    shipping_bill_no = models.CharField(max_length=30, blank=True, help_text="Indian customs export declaration")
    shipping_bill_date = models.DateField(null=True, blank=True)
    invoice_no = models.CharField("Commercial invoice no.", max_length=30, unique=True, null=True, blank=True, editable=False)
    invoice_date = models.DateField(null=True, blank=True)
    hs_codes = models.JSONField(default=dict, blank=True, help_text='HS code per style, e.g. {"NT-101": "61091000"}')
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED, editable=False, db_index=True)
    cancel_reason = models.TextField(blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(eta__isnull=True) | Q(etd__isnull=True) | Q(eta__gte=F("etd")), name="shipment_eta_after_etd"),
        ]

    def __str__(self):
        return self.shipment_no or f"Shipment #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.shipment_no:
            self.shipment_no = _number("EXP", self.created_at, self.pk)
            self.invoice_no = _number("CI", self.created_at, self.pk)
            super().save(update_fields=["shipment_no", "invoice_no"])


class ExportDocument(models.Model):
    class DocType(models.TextChoices):
        COMMERCIAL_INVOICE = "commercial_invoice", "Commercial invoice"
        PACKING_LIST = "packing_list", "Packing list"
        SHIPPING_BILL = "shipping_bill", "Shipping bill (customs)"
        BILL_OF_LADING = "bill_of_lading", "Bill of lading / AWB"
        CERTIFICATE_OF_ORIGIN = "certificate_of_origin", "Certificate of origin"
        INSPECTION_CERTIFICATE = "inspection_certificate", "Final inspection certificate"
        INSURANCE = "insurance", "Insurance certificate"
        BENEFICIARY_CERTIFICATE = "beneficiary_certificate", "Beneficiary certificate"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        SENT = "sent", "Sent to buyer / bank"
        NOT_NEEDED = "not_needed", "Not needed"

    # Generated by the ERP; the rest are entered when they arrive.
    GENERATED = [DocType.COMMERCIAL_INVOICE, DocType.PACKING_LIST, DocType.INSPECTION_CERTIFICATE]

    shipment = models.ForeignKey(ExportShipment, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    number = models.CharField(max_length=60, blank=True)
    date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["shipment", "doc_type"], name="one_doc_type_per_shipment")]


class ActivityLog(models.Model):
    class DocType(models.TextChoices):
        PACKING_LIST = "packing_list", "Packing list"
        SHIPMENT = "shipment", "Shipment"

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    doc_id = models.PositiveIntegerField()
    action = models.CharField(max_length=40)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]
