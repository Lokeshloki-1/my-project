from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from rest_framework import serializers

from apps.buyers.models import Buyer

from . import services
from .models import (
    ActivityLog,
    CostSheet,
    CostSheetLine,
    OrderConfirmation,
    OrderConfirmationLine,
    Quotation,
    QuotationLine,
)


def _user(serializer):
    return serializer.context["request"].user


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "action", "note", "user_name", "created_at"]

    def get_user_name(self, obj):
        return _name(obj.user)


class DocMixin(serializers.Serializer):
    """allowed_actions + history for the detail view."""

    doc_type = None
    actions_fn = None

    def get_allowed_actions(self, obj):
        return type(self).actions_fn(obj, _user(self))

    def get_history(self, obj):
        return ActivityLogSerializer(services.history(self.doc_type, obj.pk), many=True).data


# ---------------------------------------------------------------- cost sheets

class CostSheetLineSerializer(serializers.ModelSerializer):
    consumption = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=0)
    rate = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=0)
    wastage_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)

    class Meta:
        model = CostSheetLine
        fields = ["id", "category", "description", "unit", "consumption", "rate", "wastage_pct", "amount"]
        read_only_fields = ["amount"]


class CostSheetSerializer(DocMixin, serializers.ModelSerializer):
    doc_type = "cost_sheet"
    actions_fn = staticmethod(services.cost_sheet_actions)

    lines = CostSheetLineSerializer(many=True, required=False)
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True)
    buyer_code = serializers.CharField(source="buyer.buyer_code", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    currency = serializers.CharField(max_length=3, required=False)
    overhead_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    margin_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    commission_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=Decimal("49.99"), required=False)

    class Meta:
        model = CostSheet
        fields = [
            "id", "cost_no", "company", "buyer", "buyer_name", "buyer_code", "style_no", "style_name", "category",
            "fabric_composition", "gsm", "size_range", "quantity", "currency", "overhead_pct", "margin_pct",
            "commission_pct", "notes", "status", "status_label", "approved_by", "approved_by_name", "approved_at",
            "direct_cost", "overhead_amount", "total_cost", "margin_amount", "commission_amount", "fob_price",
            "lines", "allowed_actions", "history", "created_at", "updated_at",
        ]
        read_only_fields = [
            "cost_no", "company", "status", "approved_by", "approved_at", "direct_cost", "overhead_amount",
            "total_cost", "margin_amount", "commission_amount", "fob_price", "created_at", "updated_at",
        ]

    def get_approved_by_name(self, obj):
        return _name(obj.approved_by)

    def validate(self, attrs):
        if self.instance:
            services.ensure_draft(self.instance, "cost sheet")
            if "buyer" in attrs and attrs["buyer"] != self.instance.buyer:
                raise serializers.ValidationError({"buyer": "The buyer of a cost sheet cannot be changed. Copy it instead."})
        buyer = attrs.get("buyer")
        if buyer and buyer.status == Buyer.Status.REJECTED:
            raise serializers.ValidationError({"buyer": "This buyer was rejected."})
        if "currency" in attrs:
            attrs["currency"] = attrs["currency"].upper()
        return attrs

    def _save_lines(self, sheet, lines):
        if lines is not None:
            sheet.lines.all().delete()
            for line in lines:
                CostSheetLine.objects.create(cost_sheet=sheet, **line)  # save() computes the amount
        sheet.recalculate()

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        buyer = validated_data["buyer"]
        validated_data.setdefault("currency", buyer.preferred_currency)
        sheet = CostSheet.objects.create(company=buyer.company, created_by=_user(self), **validated_data)
        self._save_lines(sheet, lines)
        services.log("cost_sheet", sheet, "created", _user(self))
        return sheet

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        self._save_lines(instance, lines)
        return instance


class CostSheetListSerializer(CostSheetSerializer):
    class Meta(CostSheetSerializer.Meta):
        fields = [f for f in CostSheetSerializer.Meta.fields if f not in ("lines", "allowed_actions", "history")]


# ---------------------------------------------------------------- shared line logic

class _DocLineSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    style_no = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(max_length=200, required=False)
    quantity = serializers.IntegerField(min_value=1)
    cost_no = serializers.CharField(source="cost_sheet.cost_no", read_only=True)
    cost_fob_price = serializers.DecimalField(source="cost_sheet.fob_price", max_digits=14, decimal_places=2, read_only=True)
    cost_total_cost = serializers.DecimalField(source="cost_sheet.total_cost", max_digits=14, decimal_places=4, read_only=True)
    below_cost = serializers.SerializerMethodField()

    LINE_FIELDS = [
        "id", "cost_sheet", "cost_no", "style_no", "description", "quantity", "unit_price", "amount",
        "cost_fob_price", "cost_total_cost", "below_cost",
    ]

    def get_below_cost(self, obj):
        return obj.unit_price < obj.cost_sheet.total_cost


def _clean_lines(lines, buyer, currency):
    if not lines:
        raise serializers.ValidationError({"lines": "Add at least one style."})
    for line in lines:
        sheet = line["cost_sheet"]
        if sheet.buyer_id != buyer.id:
            raise serializers.ValidationError({"lines": f"Cost sheet {sheet.cost_no} is for another buyer."})
        if sheet.status != "approved":
            raise serializers.ValidationError({"lines": f"Cost sheet {sheet.cost_no} is not approved yet."})
        if sheet.currency != currency:
            raise serializers.ValidationError({"lines": f"Cost sheet {sheet.cost_no} is in {sheet.currency}, not {currency}."})
        line.setdefault("unit_price", sheet.fob_price)
        line.setdefault("style_no", sheet.style_no)
        line.setdefault("description", sheet.style_name)
    return lines


# ---------------------------------------------------------------- quotations

class QuotationLineSerializer(_DocLineSerializer):
    class Meta:
        model = QuotationLine
        fields = _DocLineSerializer.LINE_FIELDS
        read_only_fields = ["amount"]


class QuotationSerializer(DocMixin, serializers.ModelSerializer):
    doc_type = "quotation"
    actions_fn = staticmethod(services.quotation_actions)

    lines = QuotationLineSerializer(many=True)
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True)
    buyer_code = serializers.CharField(source="buyer.buyer_code", read_only=True)
    buyer_country = serializers.CharField(source="buyer.country", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    order_id = serializers.IntegerField(source="order_confirmation.id", read_only=True, default=None)
    is_expired = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    valid_until = serializers.DateField(required=False)
    currency = serializers.CharField(max_length=3, required=False)
    incoterm = serializers.ChoiceField(choices=["EXW", "FOB", "CIF", "DDP"], required=False)

    class Meta:
        model = Quotation
        fields = [
            "id", "quote_no", "company", "buyer", "buyer_name", "buyer_code", "buyer_country", "quote_date",
            "valid_until", "currency", "incoterm", "delivery_port", "payment_terms", "delivery_date", "notes",
            "status", "status_label", "reject_reason", "sent_at", "accepted_at", "is_expired", "total_quantity",
            "total_amount", "order_id", "lines", "allowed_actions", "history", "created_at", "updated_at",
        ]
        read_only_fields = [
            "quote_no", "company", "status", "reject_reason", "sent_at", "accepted_at", "total_quantity",
            "total_amount", "created_at", "updated_at",
        ]

    def get_is_expired(self, obj):
        from django.utils import timezone
        return obj.status in ("draft", "sent") and obj.valid_until < timezone.localdate()

    def validate(self, attrs):
        if self.instance:
            services.ensure_draft(self.instance, "quotation")
            if "buyer" in attrs and attrs["buyer"] != self.instance.buyer:
                raise serializers.ValidationError({"buyer": "The buyer of a quotation cannot be changed."})
        buyer = attrs.get("buyer", getattr(self.instance, "buyer", None))
        services.require_approved_buyer(buyer)
        quote_date = attrs.get("quote_date", getattr(self.instance, "quote_date", None))
        attrs.setdefault("valid_until", getattr(self.instance, "valid_until", None) or quote_date + timedelta(days=30))
        if attrs["valid_until"] < quote_date:
            raise serializers.ValidationError({"valid_until": "Valid-until must be on or after the quotation date."})
        currency = (attrs.get("currency") or getattr(self.instance, "currency", None) or buyer.preferred_currency).upper()
        attrs["currency"] = currency
        if "lines" in attrs:
            _clean_lines(attrs["lines"], buyer, currency)
        return attrs

    def _save_lines(self, quote, lines):
        if lines is not None:
            quote.lines.all().delete()
            for line in lines:
                QuotationLine.objects.create(quotation=quote, **line)
        quote.recalculate()

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        buyer = validated_data["buyer"]
        validated_data.setdefault("incoterm", buyer.default_incoterm)
        credit = services.latest_passed_credit(buyer)
        if credit and "payment_terms" not in self.initial_data:
            validated_data["payment_terms"] = credit.payment_terms
        quote = Quotation.objects.create(company=buyer.company, created_by=_user(self), **validated_data)
        self._save_lines(quote, lines)
        services.log("quotation", quote, "created", _user(self))
        return quote

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        self._save_lines(instance, lines)
        return instance


class QuotationListSerializer(QuotationSerializer):
    class Meta(QuotationSerializer.Meta):
        fields = [f for f in QuotationSerializer.Meta.fields if f not in ("lines", "allowed_actions", "history")]


# ---------------------------------------------------------------- order confirmations

class OrderLineSerializer(_DocLineSerializer):
    class Meta:
        model = OrderConfirmationLine
        fields = _DocLineSerializer.LINE_FIELDS
        read_only_fields = ["amount"]


class OrderConfirmationSerializer(DocMixin, serializers.ModelSerializer):
    doc_type = "order"
    actions_fn = staticmethod(services.order_actions)

    lines = OrderLineSerializer(many=True, required=False)
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True)
    buyer_code = serializers.CharField(source="buyer.buyer_code", read_only=True)
    quote_no = serializers.CharField(source="quotation.quote_no", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    confirmed_by_name = serializers.SerializerMethodField()
    credit = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = OrderConfirmation
        fields = [
            "id", "oc_no", "company", "buyer", "buyer_name", "buyer_code", "quotation", "quote_no", "buyer_po_no",
            "po_date", "ship_date", "currency", "incoterm", "payment_terms", "delivery_port", "notes", "status",
            "status_label", "credit_override", "override_reason", "confirmed_by", "confirmed_by_name", "confirmed_at",
            "cancel_reason", "total_quantity", "total_amount", "credit", "lines", "allowed_actions", "history",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "oc_no", "company", "buyer", "quotation", "currency", "incoterm", "payment_terms", "status",
            "credit_override", "override_reason", "confirmed_by", "confirmed_at", "cancel_reason",
            "total_quantity", "total_amount", "created_at", "updated_at",
        ]

    def get_confirmed_by_name(self, obj):
        return _name(obj.confirmed_by)

    def get_credit(self, obj):
        return services.credit_position(obj)

    def validate(self, attrs):
        services.ensure_draft(self.instance, "order")
        if "lines" in attrs:
            _clean_lines(attrs["lines"], self.instance.buyer, self.instance.currency)
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        if lines is not None:
            instance.lines.all().delete()
            for line in lines:
                OrderConfirmationLine.objects.create(order=instance, **line)
        instance.recalculate()
        return instance


class OrderConfirmationListSerializer(OrderConfirmationSerializer):
    class Meta(OrderConfirmationSerializer.Meta):
        fields = [f for f in OrderConfirmationSerializer.Meta.fields if f not in ("lines", "allowed_actions", "history", "credit")]
