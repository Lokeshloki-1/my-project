"""
Buyer onboarding for a textile exporter.

    Buyer Enquiry -> Buyer Registration -> Buyer Profile -> Contact Details
    -> Buyer Requirements -> Credit Verification -> Buyer Approval

A Buyer's status only changes through apps.buyers.services (never from a form),
so every change is checked and written to BuyerStatusLog. Approving a buyer
creates the sales.Customer that quotations, orders and invoices use.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q


def _number(prefix, when, pk):
    # Derived from the primary key, so it is unique without race conditions.
    return f"{prefix}-{when:%Y}-{pk:06d}"


class BuyerEnquiry(models.Model):
    class Source(models.TextChoices):
        EMAIL = "email", "Email"
        WEBSITE = "website", "Website"
        TRADE_FAIR = "trade_fair", "Trade fair"
        AGENT = "agent", "Buying agent"
        REFERRAL = "referral", "Referral"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        QUALIFIED = "qualified", "Qualified"
        CONVERTED = "converted", "Converted"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="buyer_enquiries")
    enquiry_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.EMAIL)
    buyer_name = models.CharField("Buyer company name", max_length=200)
    contact_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=100)
    product_interest = models.TextField(blank=True, help_text="Products asked about, e.g. men's knit polo, 180 GSM")
    expected_volume = models.PositiveIntegerField(null=True, blank=True, help_text="Expected pieces per year")
    received_on = models.DateField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="buyer_enquiries"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    reject_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        verbose_name_plural = "buyer enquiries"

    def __str__(self):
        return f"{self.enquiry_no or 'Enquiry'} - {self.buyer_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.enquiry_no:
            self.enquiry_no = _number("ENQ", self.received_on, self.pk)
            super().save(update_fields=["enquiry_no"])


class Buyer(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        PENDING_CREDIT = "pending_credit", "Pending credit check"
        CREDIT_FAILED = "credit_failed", "Credit failed"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    # Profile, contacts and requirements can be edited by anyone only in these statuses.
    EDITABLE_STATUSES = [Status.REGISTERED, Status.CREDIT_FAILED]

    class BuyerType(models.TextChoices):
        BRAND = "brand", "Brand"
        RETAILER = "retailer", "Retailer"
        IMPORTER = "importer", "Importer"
        WHOLESALER = "wholesaler", "Wholesaler"
        BUYING_AGENT = "buying_agent", "Buying agent"

    class Incoterm(models.TextChoices):
        EXW = "EXW", "EXW - Ex works"
        FOB = "FOB", "FOB - Free on board"
        CIF = "CIF", "CIF - Cost, insurance & freight"
        DDP = "DDP", "DDP - Delivered duty paid"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="buyers")
    buyer_code = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    enquiry = models.OneToOneField(
        BuyerEnquiry, on_delete=models.PROTECT, null=True, blank=True, related_name="buyer"
    )

    # Registration
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    buyer_type = models.CharField(max_length=20, choices=BuyerType.choices, default=BuyerType.BRAND)
    country = models.CharField(max_length=100)

    # Profile
    city = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    tax_id = models.CharField("Tax / VAT ID", max_length=30, blank=True)
    website = models.URLField(blank=True)
    year_established = models.PositiveSmallIntegerField(null=True, blank=True)
    annual_turnover = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True, help_text="In the preferred currency"
    )
    preferred_currency = models.CharField(max_length=3, default="USD")
    default_incoterm = models.CharField(max_length=3, choices=Incoterm.choices, default=Incoterm.FOB)
    bank_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)

    # Workflow
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REGISTERED, editable=False, db_index=True
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name="approved_buyers",
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    rejection_reason = models.TextField(blank=True, editable=False)
    customer = models.OneToOneField(
        "sales.Customer", on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="buyer"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="created_buyers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(annual_turnover__isnull=True) | Q(annual_turnover__gte=0), name="buyer_turnover_non_negative"
            ),
            models.CheckConstraint(
                condition=~Q(status="approved") | Q(customer__isnull=False), name="approved_buyer_has_customer"
            ),
        ]

    def __str__(self):
        return f"{self.buyer_code or 'Buyer'} - {self.legal_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.buyer_code:
            self.buyer_code = _number("BYR", self.created_at, self.pk)
            super().save(update_fields=["buyer_code"])

    @property
    def is_editable(self):
        return self.status in self.EDITABLE_STATUSES


class BuyerContact(models.Model):
    class Department(models.TextChoices):
        MERCHANDISING = "merchandising", "Merchandising"
        SOURCING = "sourcing", "Sourcing"
        QA = "qa", "Quality assurance"
        ACCOUNTS = "accounts", "Accounts"
        LOGISTICS = "logistics", "Logistics"
        MANAGEMENT = "management", "Management"

    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=20, choices=Department.choices, default=Department.MERCHANDISING)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(fields=["buyer"], condition=Q(is_primary=True), name="one_primary_contact_per_buyer"),
            models.CheckConstraint(condition=~Q(email="") | ~Q(phone=""), name="contact_has_email_or_phone"),
        ]

    def __str__(self):
        return self.name


class BuyerRequirement(models.Model):
    class Category(models.TextChoices):
        KNITS = "knits", "Knits"
        WOVENS = "wovens", "Wovens"
        DENIM = "denim", "Denim"
        ACTIVEWEAR = "activewear", "Activewear"
        INNERWEAR = "innerwear", "Innerwear"
        KIDSWEAR = "kidswear", "Kidswear"
        HOME_TEXTILES = "home_textiles", "Home textiles"
        FABRIC = "fabric", "Fabric"
        YARN = "yarn", "Yarn"

    class Certification(models.TextChoices):
        GOTS = "GOTS", "GOTS"
        OEKO_TEX = "OEKO-TEX", "OEKO-TEX"
        BSCI = "BSCI", "amfori BSCI"
        SEDEX = "SEDEX", "SEDEX / SMETA"
        WRAP = "WRAP", "WRAP"
        GRS = "GRS", "GRS"
        OCS = "OCS", "OCS"
        BCI = "BCI", "Better Cotton"
        ISO_9001 = "ISO 9001", "ISO 9001"

    buyer = models.OneToOneField(Buyer, on_delete=models.CASCADE, related_name="requirement")
    product_categories = models.JSONField(default=list, blank=True)
    fabric_composition = models.CharField(max_length=200, blank=True, help_text="e.g. 100% cotton, 60/40 CVC")
    gsm_min = models.PositiveIntegerField(null=True, blank=True)
    gsm_max = models.PositiveIntegerField(null=True, blank=True)
    size_range = models.CharField(max_length=100, blank=True, help_text="e.g. XS-XXL, 2-14Y")
    annual_volume = models.PositiveIntegerField(null=True, blank=True, help_text="Pieces per year")
    target_price_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    target_price_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_currency = models.CharField(max_length=3, default="USD")
    certifications = models.JSONField(default=list, blank=True)
    packaging = models.TextField(blank=True)
    labelling = models.TextField(blank=True)
    testing_lab = models.CharField(max_length=100, blank=True, help_text="e.g. SGS, Intertek, BV")
    delivery_port = models.CharField(max_length=100, blank=True)
    payment_terms_requested = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(gsm_min__isnull=True) | Q(gsm_max__isnull=True) | Q(gsm_min__lte=F("gsm_max")),
                name="requirement_gsm_range",
            ),
            models.CheckConstraint(
                condition=Q(target_price_min__isnull=True) | Q(target_price_min__gte=0), name="requirement_price_min_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(target_price_min__isnull=True) | Q(target_price_max__isnull=True)
                | Q(target_price_min__lte=F("target_price_max")),
                name="requirement_price_range",
            ),
        ]

    def __str__(self):
        return f"Requirements of {self.buyer}"


class CreditCheck(models.Model):
    class PaymentTerms(models.TextChoices):
        ADVANCE = "advance", "100% advance"
        LC_SIGHT = "lc_sight", "LC at sight"
        LC_USANCE = "lc_usance", "LC usance"
        TT_30 = "tt_30", "TT 30 days"
        TT_60 = "tt_60", "TT 60 days"
        TT_90 = "tt_90", "TT 90 days"
        DA = "da", "DA (documents against acceptance)"
        DP = "dp", "DP (documents against payment)"

    class Risk(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Result(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    buyer = models.ForeignKey(Buyer, on_delete=models.PROTECT, related_name="credit_checks")
    requested_limit = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    approved_limit = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    payment_terms = models.CharField(max_length=20, choices=PaymentTerms.choices)
    risk_rating = models.CharField(max_length=10, choices=Risk.choices)
    bank_reference = models.TextField(blank=True)
    trade_references = models.TextField(blank=True)
    ecgc_cover = models.BooleanField("ECGC cover", default=False, help_text="Export credit insurance in place")
    result = models.CharField(max_length=10, choices=Result.choices)
    remarks = models.TextField(blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_checks")
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at", "-id"]
        get_latest_by = ["checked_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_limit__gte=0) & Q(approved_limit__gte=0), name="credit_limits_non_negative"
            ),
            models.CheckConstraint(condition=~Q(result="fail") | Q(approved_limit=0), name="failed_credit_has_no_limit"),
        ]

    def __str__(self):
        return f"Credit check {self.result} for {self.buyer}"


class BuyerStatusLog(models.Model):
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.buyer}: {self.from_status or '-'} -> {self.to_status}"
