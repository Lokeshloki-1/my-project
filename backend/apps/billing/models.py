"""
Invoices and payments.

An invoice is created from a confirmed sales order and copies its amounts, so
later price changes never alter an issued invoice. Payments reduce the balance;
the invoice status (and the sales order status) follow automatically.
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum


class Invoice(models.Model):
    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    sales_order = models.OneToOneField("sales.SalesOrder", on_delete=models.PROTECT, related_name="invoice")
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="invoices")
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="invoices")
    invoice_no = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    total = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNPAID, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(due_date__gte=models.F("invoice_date")), name="invoice_due_after_date"),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0) & Q(amount_paid__lte=models.F("total")),
                name="invoice_paid_within_total",
            ),
        ]

    def __str__(self):
        return self.invoice_no or f"Invoice #{self.pk}"

    @property
    def balance(self):
        return self.total - self.amount_paid

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.invoice_no:
            self.invoice_no = f"INV-{self.invoice_date:%Y}-{self.pk:06d}"
            super().save(update_fields=["invoice_no"])

    def refresh_payment_status(self):
        """Recalculate amount paid and status from the payments. Call inside a transaction."""
        from apps.sales.models import SalesOrder

        paid = self.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        self.amount_paid = paid
        if self.status != self.Status.CANCELLED:
            if paid >= self.total:
                self.status = self.Status.PAID
            elif paid > 0:
                self.status = self.Status.PARTIALLY_PAID
            else:
                self.status = self.Status.UNPAID
        self.save(update_fields=["amount_paid", "status", "updated_at"])

        order_status = SalesOrder.Status.PAID if self.status == self.Status.PAID else SalesOrder.Status.INVOICED
        if self.status != self.Status.CANCELLED and self.sales_order.status != order_status:
            self.sales_order.status = order_status
            self.sales_order.save(update_fields=["status", "updated_at"])


class Payment(models.Model):
    class Method(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank transfer (NEFT/RTGS)"
        UPI = "upi", "UPI"
        CHEQUE = "cheque", "Cheque"
        CASH = "cash", "Cash"
        CARD = "card", "Card"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.BANK_TRANSFER)
    reference = models.CharField(max_length=100, blank=True, help_text="UTR / cheque no. / transaction id")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
        ]

    def __str__(self):
        return f"{self.amount} on {self.payment_date} for {self.invoice}"
