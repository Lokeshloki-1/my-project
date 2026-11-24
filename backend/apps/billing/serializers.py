from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.sales.models import SalesOrder
from apps.sales.serializers import SalesOrderItemSerializer

from .models import Invoice, Payment


class PaymentSerializer(serializers.ModelSerializer):
    invoice_no = serializers.CharField(source="invoice.invoice_no", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer.name", read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = Payment
        fields = [
            "id", "invoice", "invoice_no", "customer_name", "payment_date", "amount",
            "method", "reference", "notes", "created_at",
        ]
        read_only_fields = ["created_at"]

    @transaction.atomic
    def create(self, validated_data):
        # Lock the invoice row so two payments at the same moment can't overpay it.
        invoice = Invoice.objects.select_for_update().get(pk=validated_data["invoice"].pk)
        if invoice.status == Invoice.Status.CANCELLED:
            raise serializers.ValidationError({"invoice": "This invoice is cancelled."})
        if validated_data["amount"] > invoice.balance:
            raise serializers.ValidationError({"amount": f"Amount is more than the balance due ({invoice.balance})."})
        if validated_data["payment_date"] < invoice.invoice_date:
            raise serializers.ValidationError({"payment_date": "Cannot be before the invoice date."})
        payment = Payment.objects.create(**validated_data)
        invoice.refresh_payment_status()
        return payment


class InvoiceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    order_no = serializers.CharField(source="sales_order.order_no", read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_overdue = serializers.SerializerMethodField()
    # Used only when creating: due date = invoice date + payment terms.
    payment_terms_days = serializers.IntegerField(write_only=True, required=False, default=30, min_value=0, max_value=365)

    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_no", "sales_order", "order_no", "company", "company_name", "customer", "customer_name",
            "invoice_date", "due_date", "payment_terms_days", "subtotal", "tax_amount", "total",
            "amount_paid", "balance", "status", "is_overdue", "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "company", "customer", "subtotal", "tax_amount", "total", "amount_paid", "status",
            "created_at", "updated_at",
        ]
        extra_kwargs = {"invoice_date": {"required": False}, "due_date": {"required": False}}

    def get_is_overdue(self, obj):
        return obj.status in (Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID) and obj.due_date < timezone.localdate()

    def validate(self, attrs):
        if self.instance:
            if "sales_order" in attrs and attrs["sales_order"] != self.instance.sales_order:
                raise serializers.ValidationError({"sales_order": "An invoice's order cannot be changed."})
            if "invoice_date" in attrs and attrs["invoice_date"] != self.instance.invoice_date:
                raise serializers.ValidationError({"invoice_date": "An issued invoice's date cannot be changed."})
            due = attrs.get("due_date", self.instance.due_date)
            if due < self.instance.invoice_date:
                raise serializers.ValidationError({"due_date": "Cannot be before the invoice date."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        order = SalesOrder.objects.select_for_update().get(pk=validated_data["sales_order"].pk)
        if order.status != SalesOrder.Status.CONFIRMED:
            raise serializers.ValidationError({"sales_order": "Only confirmed orders can be invoiced."})
        if Invoice.objects.filter(sales_order=order).exists():
            raise serializers.ValidationError({"sales_order": "This order already has an invoice."})
        terms = validated_data.pop("payment_terms_days", 30)
        invoice_date = validated_data.get("invoice_date") or timezone.localdate()
        due_date = validated_data.get("due_date") or invoice_date + timedelta(days=terms)
        if due_date < invoice_date:
            raise serializers.ValidationError({"due_date": "Cannot be before the invoice date."})
        invoice = Invoice.objects.create(
            sales_order=order, company=order.company, customer=order.customer,
            invoice_date=invoice_date, due_date=due_date, notes=validated_data.get("notes", ""),
            subtotal=order.subtotal, tax_amount=order.tax_amount, total=order.total,
        )
        order.status = SalesOrder.Status.INVOICED
        order.save(update_fields=["status", "updated_at"])
        return invoice

    def update(self, instance, validated_data):
        validated_data.pop("payment_terms_days", None)
        instance.due_date = validated_data.get("due_date", instance.due_date)
        instance.notes = validated_data.get("notes", instance.notes)
        instance.save(update_fields=["due_date", "notes", "updated_at"])
        return instance


class InvoiceDetailSerializer(InvoiceSerializer):
    items = SalesOrderItemSerializer(source="sales_order.items", many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ["items", "payments"]
