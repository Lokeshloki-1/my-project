"""
Textile flow, step 9:  Sales Invoice → Payment → Receivables → Profit  (export sales, buyer's currency).

    invoice amount        = Σ shipped pcs × order price per style        (invoice currency)
    invoice INR           = amount × invoice exchange rate                (e.g. the shipping-bill rate)
    receipt INR           = amount received × realised rate
    exchange gain / loss  = (amount received + bank charges) × (realised rate − invoice rate)
    balance               = amount − Σ (received + bank charges)

Domestic INR invoices with GST stay in apps.billing; export money is never mixed into them.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

TWO = Decimal("0.01")


def q2(v):
    return Decimal(v).quantize(TWO, ROUND_HALF_UP)


class ExportInvoice(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTIALLY_PAID = "partially_paid", "Partly paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="export_invoices")
    shipment = models.OneToOneField("exports.ExportShipment", on_delete=models.PROTECT, related_name="export_invoice")
    order = models.ForeignKey("merchandising.OrderConfirmation", on_delete=models.PROTECT, related_name="export_invoices")
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="export_invoices")
    invoice_no = models.CharField(max_length=30, unique=True)
    invoice_date = models.DateField(db_index=True)
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, help_text="INR per unit of the invoice currency")
    amount_inr = models.DecimalField(max_digits=18, decimal_places=2, editable=False)
    payment_terms = models.CharField(max_length=20)
    due_date = models.DateField(db_index=True)
    amount_received = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    bank_charges = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, editable=False, db_index=True)
    cancel_reason = models.TextField(blank=True, editable=False)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        indexes = [models.Index(fields=["buyer", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0) & Q(exchange_rate__gt=0), name="export_invoice_amount_rate_valid"),
            models.CheckConstraint(condition=Q(amount_received__gte=0) & Q(bank_charges__gte=0)
                                   & Q(amount__gte=F("amount_received") + F("bank_charges")), name="export_invoice_settled_within_amount"),
            models.CheckConstraint(condition=Q(due_date__gte=F("invoice_date")), name="export_invoice_due_after_date"),
        ]

    def __str__(self):
        return self.invoice_no

    @property
    def balance(self):
        return self.amount - self.amount_received - self.bank_charges

    def save(self, *args, **kwargs):
        self.amount_inr = q2(self.amount * self.exchange_rate)
        super().save(*args, **kwargs)


class ExportReceipt(models.Model):
    class Method(models.TextChoices):
        TT = "tt", "Telegraphic transfer (TT)"
        LC = "lc", "Letter of credit"
        DA_DP = "da_dp", "Collection (DA / DP)"
        ADVANCE = "advance", "Advance"

    invoice = models.ForeignKey(ExportInvoice, on_delete=models.PROTECT, related_name="receipts")
    received_on = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2, help_text="Credited, in the invoice currency")
    bank_charges = models.DecimalField(max_digits=16, decimal_places=2, default=0, help_text="Deducted by banks, in the invoice currency")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, help_text="Realised INR per unit")
    amount_inr = models.DecimalField(max_digits=18, decimal_places=2, editable=False)
    exchange_gain_loss_inr = models.DecimalField(max_digits=16, decimal_places=2, editable=False)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.TT)
    bank_reference = models.CharField("FIRC / BRC / bank ref.", max_length=60, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0) & Q(bank_charges__gte=0) & Q(exchange_rate__gt=0), name="export_receipt_values_valid"),
        ]

    def save(self, *args, **kwargs):
        self.amount_inr = q2(self.amount * self.exchange_rate)
        self.exchange_gain_loss_inr = q2((self.amount + self.bank_charges) * (self.exchange_rate - self.invoice.exchange_rate))
        super().save(*args, **kwargs)


class OrderExpense(models.Model):
    class Category(models.TextChoices):
        FREIGHT = "freight", "Freight"
        CLEARING = "clearing", "Clearing / CHA"
        COURIER = "courier", "Courier (samples, documents)"
        TESTING = "testing", "Testing / inspection"
        COMMISSION = "commission", "Agent commission"
        BANK = "bank", "Bank charges (local)"
        OTHER = "other", "Other"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="order_expenses")
    order = models.ForeignKey("merchandising.OrderConfirmation", on_delete=models.PROTECT, related_name="expenses")
    date = models.DateField()
    category = models.CharField(max_length=20, choices=Category.choices)
    amount_inr = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [models.CheckConstraint(condition=Q(amount_inr__gt=0), name="order_expense_positive")]
