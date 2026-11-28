from datetime import date
from decimal import Decimal

from rest_framework import serializers

from apps.buyers.models import CreditCheck

from . import services
from .models import ExportInvoice, ExportReceipt, OrderExpense


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class ExportReceiptSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal("0.01"))
    bank_charges = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal("0"), required=False)
    exchange_rate = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=Decimal("0.0001"))
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    invoice_no = serializers.CharField(source="invoice.invoice_no", read_only=True)
    currency = serializers.CharField(source="invoice.currency", read_only=True)

    class Meta:
        model = ExportReceipt
        fields = ["id", "invoice", "invoice_no", "currency", "received_on", "amount", "bank_charges", "exchange_rate", "amount_inr",
                  "exchange_gain_loss_inr", "method", "method_label", "bank_reference", "note", "created_by_name", "created_at"]
        read_only_fields = ["amount_inr", "exchange_gain_loss_inr", "created_at"]

    def get_created_by_name(self, obj):
        return _name(obj.created_by)

    def create(self, validated_data):
        return services.record_receipt(validated_data.pop("invoice"), self.context["request"].user, validated_data)


class ExportInvoiceSerializer(serializers.ModelSerializer):
    receipts = ExportReceiptSerializer(many=True, read_only=True)
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True)
    oc_no = serializers.CharField(source="order.oc_no", read_only=True)
    buyer_po_no = serializers.CharField(source="order.buyer_po_no", read_only=True)
    shipment_no = serializers.CharField(source="shipment.shipment_no", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_terms_label = serializers.SerializerMethodField()
    balance = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    balance_inr = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    gain_loss_inr = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = ExportInvoice
        fields = ["id", "invoice_no", "company", "shipment", "shipment_no", "order", "oc_no", "buyer", "buyer_name", "buyer_po_no",
                  "invoice_date", "currency", "amount", "exchange_rate", "amount_inr", "payment_terms", "payment_terms_label",
                  "due_date", "amount_received", "bank_charges", "balance", "balance_inr", "days_overdue", "status", "status_label",
                  "cancel_reason", "notes", "lines", "receipts", "gain_loss_inr", "allowed_actions", "created_at"]
        read_only_fields = ["invoice_no", "company", "shipment", "order", "buyer", "invoice_date", "currency", "amount", "exchange_rate",
                            "payment_terms", "status", "cancel_reason", "created_at"]

    def get_payment_terms_label(self, obj):
        return dict(CreditCheck.PaymentTerms.choices).get(obj.payment_terms, obj.payment_terms)

    def get_balance_inr(self, obj):
        return (obj.balance * obj.exchange_rate).quantize(Decimal("0.01"))

    def get_days_overdue(self, obj):
        if obj.status not in (ExportInvoice.Status.OPEN, ExportInvoice.Status.PARTIALLY_PAID):
            return 0
        return max((date.today() - obj.due_date).days, 0)

    def get_lines(self, obj):
        return services.invoice_lines(obj.shipment)

    def get_gain_loss_inr(self, obj):
        return sum((r.exchange_gain_loss_inr for r in obj.receipts.all()), Decimal("0"))

    def get_allowed_actions(self, obj):
        return services.invoice_actions(obj, self.context["request"].user)

    def validate(self, attrs):
        inst = self.instance
        if inst and inst.status == ExportInvoice.Status.CANCELLED:
            raise services.Conflict("This invoice is cancelled.")
        due = attrs.get("due_date")
        if due and inst and due < inst.invoice_date:
            raise serializers.ValidationError({"due_date": "The due date can't be before the invoice date."})
        return attrs


class ExportInvoiceListSerializer(ExportInvoiceSerializer):
    class Meta(ExportInvoiceSerializer.Meta):
        fields = ["id", "invoice_no", "shipment", "shipment_no", "order", "oc_no", "buyer_name", "invoice_date", "currency", "amount",
                  "amount_inr", "due_date", "amount_received", "balance", "days_overdue", "status", "status_label"]


class OrderExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    oc_no = serializers.CharField(source="order.oc_no", read_only=True)
    amount_inr = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = OrderExpense
        fields = ["id", "order", "oc_no", "date", "category", "category_label", "amount_inr", "note", "created_at"]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        order = validated_data["order"]
        return OrderExpense.objects.create(company=order.company, created_by=self.context["request"].user, **validated_data)
