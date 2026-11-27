from decimal import Decimal

from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import serializers

from apps.development.models import BOMItem

from . import services
from .models import (
    ActivityLog,
    MaterialRequirement,
    PurchaseOrder,
    PurchaseOrderLine,
    RequirementLine,
    RFQ,
    RFQLine,
    Supplier,
)

ZERO = Decimal("0")


def _user(s):
    return s.context["request"].user


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "action", "note", "user_name", "created_at"]

    def get_user_name(self, obj):
        return _name(obj.user)


class HistoryMixin:
    doc_type = None

    def get_history(self, obj):
        return ActivityLogSerializer(services.history(self.doc_type, obj.pk), many=True).data


# ---------------------------------------------------------------- suppliers

class SupplierSerializer(serializers.ModelSerializer):
    categories = serializers.ListField(child=serializers.ChoiceField(choices=BOMItem.Category.choices), required=False)

    class Meta:
        model = Supplier
        fields = [
            "id", "company", "name", "contact_name", "email", "phone", "city", "country", "address", "tax_id",
            "categories", "payment_terms", "lead_time_days", "is_active", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        if self.instance and "company" in attrs and attrs["company"] != self.instance.company:
            raise serializers.ValidationError({"company": "The company of a supplier cannot be changed."})
        if "categories" in attrs:
            attrs["categories"] = list(dict.fromkeys(attrs["categories"]))
        return attrs


# ---------------------------------------------------------------- requirements

def ordered_of(line):
    """Ordered quantity on PO lines that are not cancelled (uses prefetched po_lines__order)."""
    return sum((pl.quantity for pl in line.po_lines.all() if pl.order.status != PurchaseOrder.Status.CANCELLED), ZERO)


class RequirementLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    required_qty = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=ZERO)
    ordered_qty = serializers.SerializerMethodField()
    open_qty = serializers.SerializerMethodField()
    rfq_nos = serializers.SerializerMethodField()
    po_nos = serializers.SerializerMethodField()

    class Meta:
        model = RequirementLine
        fields = [
            "id", "category", "description", "colour", "unit", "supplier_hint", "styles", "net_qty", "required_qty",
            "ordered_qty", "open_qty", "rfq_nos", "po_nos",
        ]
        read_only_fields = ["net_qty", "styles"]

    def get_ordered_qty(self, obj):
        return ordered_of(obj) if obj.pk else ZERO

    def get_open_qty(self, obj):
        return max(obj.required_qty - ordered_of(obj), ZERO) if obj.pk else obj.required_qty

    def get_rfq_nos(self, obj):
        return sorted({rl.rfq.rfq_no for rl in obj.rfq_lines.all() if rl.rfq.status != RFQ.Status.CANCELLED}) if obj.pk else []

    def get_po_nos(self, obj):
        return sorted({pl.order.po_no for pl in obj.po_lines.all() if pl.order.status != PurchaseOrder.Status.CANCELLED}) if obj.pk else []


class MaterialRequirementSerializer(HistoryMixin, serializers.ModelSerializer):
    doc_type = "requirement"
    lines = RequirementLineSerializer(many=True, required=False)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    oc_no = serializers.CharField(source="order.oc_no", read_only=True, default=None)
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True, default=None)
    approved_by_name = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    wastage_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=ZERO, max_value=Decimal("100"), required=False)

    class Meta:
        model = MaterialRequirement
        fields = [
            "id", "mr_no", "company", "order", "oc_no", "buyer", "buyer_name", "title", "needed_by", "wastage_pct",
            "notes", "warnings", "status", "status_label", "approved_by_name", "approved_at", "progress", "lines",
            "allowed_actions", "history", "created_at", "updated_at",
        ]
        read_only_fields = ["mr_no", "order", "buyer", "warnings", "status", "approved_at", "created_at", "updated_at"]

    def get_approved_by_name(self, obj):
        return _name(obj.approved_by)

    def get_progress(self, obj):
        lines = list(obj.lines.all())
        done = sum(1 for line in lines if ordered_of(line) >= line.required_qty)
        return {"lines": len(lines), "fully_ordered": done}

    def get_allowed_actions(self, obj):
        return services.requirement_actions(obj, _user(self))

    def validate(self, attrs):
        if self.instance:
            services.ensure_draft(self.instance, "requirement")
            if "company" in attrs and attrs["company"] != self.instance.company:
                raise serializers.ValidationError({"company": "The company cannot be changed."})
        return attrs

    def _save_lines(self, mr, lines):
        if lines is None:
            return
        keep = []
        for i, data in enumerate(lines):
            line_id = data.pop("id", None)
            line = mr.lines.filter(pk=line_id).first() if line_id else None
            if line is None:
                line = RequirementLine(requirement=mr)
            for k, v in data.items():
                setattr(line, k, v)
            line.position = i
            line.save()
            keep.append(line.pk)
        try:
            mr.lines.exclude(pk__in=keep).delete()
        except ProtectedError:
            raise serializers.ValidationError({"lines": "A removed line is already on an RFQ or PO."}) from None

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        mr = MaterialRequirement.objects.create(created_by=_user(self), **validated_data)
        self._save_lines(mr, lines)
        services.log("requirement", mr, "created", _user(self), "Entered by hand")
        return mr

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        self._save_lines(instance, lines)
        return instance


class MaterialRequirementListSerializer(MaterialRequirementSerializer):
    class Meta(MaterialRequirementSerializer.Meta):
        fields = ["id", "mr_no", "company", "order", "oc_no", "buyer_name", "title", "needed_by", "status",
                  "status_label", "progress", "warnings", "created_at"]


# ---------------------------------------------------------------- RFQs

class _DocLineSerializer(serializers.ModelSerializer):
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    mr_no = serializers.CharField(source="requirement_line.requirement.mr_no", read_only=True, default=None)


class RFQLineSerializer(_DocLineSerializer):
    class Meta:
        model = RFQLine
        fields = ["id", "requirement_line", "mr_no", "category", "description", "colour", "unit", "quantity"]


class RFQSerializer(HistoryMixin, serializers.ModelSerializer):
    doc_type = "rfq"
    lines = RFQLineSerializer(many=True)
    suppliers = serializers.PrimaryKeyRelatedField(many=True, queryset=Supplier.objects.all(), required=False)
    supplier_names = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    mr_no = serializers.CharField(source="requirement.mr_no", read_only=True, default=None)
    awarded_supplier_name = serializers.CharField(source="awarded_supplier.name", read_only=True, default=None)
    po_id = serializers.SerializerMethodField()
    comparison = serializers.SerializerMethodField()
    quote_count = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = RFQ
        fields = [
            "id", "rfq_no", "company", "requirement", "mr_no", "title", "reply_by", "required_by", "currency", "notes",
            "suppliers", "supplier_names", "status", "status_label", "sent_at", "awarded_supplier",
            "awarded_supplier_name", "po_id", "quote_count", "lines", "comparison", "allowed_actions", "history",
            "created_at", "updated_at",
        ]
        read_only_fields = ["rfq_no", "status", "sent_at", "awarded_supplier", "created_at", "updated_at"]

    def get_supplier_names(self, obj):
        return [s.name for s in obj.suppliers.all()]

    def get_po_id(self, obj):
        po = obj.purchase_orders.first()
        return po.id if po else None

    def get_comparison(self, obj):
        return services.comparison(obj)

    def get_quote_count(self, obj):
        return obj.quotes.count()

    def get_allowed_actions(self, obj):
        return services.rfq_actions(obj, _user(self))

    def validate(self, attrs):
        if self.instance:
            services.ensure_draft(self.instance, "RFQ")
            if "company" in attrs and attrs["company"] != self.instance.company:
                raise serializers.ValidationError({"company": "The company cannot be changed."})
        company = attrs.get("company", getattr(self.instance, "company", None))
        req = attrs.get("requirement", getattr(self.instance, "requirement", None))
        if req and req.company_id != company.id:
            raise serializers.ValidationError({"requirement": "That requirement is for another company."})
        if req and req.status != MaterialRequirement.Status.APPROVED:
            raise serializers.ValidationError({"requirement": "The requirement must be approved first."})
        for s in attrs.get("suppliers", []):
            if s.company_id != company.id or not s.is_active:
                raise serializers.ValidationError({"suppliers": f"{s.name} is not an active supplier of this company."})
        if "lines" in attrs:
            if not attrs["lines"]:
                raise serializers.ValidationError({"lines": "Add at least one material."})
            services.check_requirement_lines(attrs["lines"], company)
        if "currency" in attrs:
            attrs["currency"] = attrs["currency"].upper()
        return attrs

    def _save(self, rfq, lines, suppliers):
        if suppliers is not None:
            rfq.suppliers.set(suppliers)
        if lines is not None:
            rfq.lines.all().delete()
            RFQLine.objects.bulk_create([RFQLine(rfq=rfq, position=i, **line) for i, line in enumerate(lines)])

    @transaction.atomic
    def create(self, validated_data):
        lines, suppliers = validated_data.pop("lines"), validated_data.pop("suppliers", [])
        rfq = RFQ.objects.create(created_by=_user(self), **validated_data)
        self._save(rfq, lines, suppliers)
        services.log("rfq", rfq, "created", _user(self))
        return rfq

    @transaction.atomic
    def update(self, instance, validated_data):
        lines, suppliers = validated_data.pop("lines", None), validated_data.pop("suppliers", None)
        instance = super().update(instance, validated_data)
        self._save(instance, lines, suppliers)
        return instance


class RFQListSerializer(RFQSerializer):
    class Meta(RFQSerializer.Meta):
        fields = ["id", "rfq_no", "company", "mr_no", "title", "reply_by", "status", "status_label", "supplier_names",
                  "quote_count", "awarded_supplier_name", "created_at"]


class QuoteLineInputSerializer(serializers.Serializer):
    rfq_line = serializers.PrimaryKeyRelatedField(queryset=RFQLine.objects.all())
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=ZERO)
    lead_time_days = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class QuoteInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    currency = serializers.CharField(max_length=3, required=False, default="INR")
    valid_until = serializers.DateField(required=False, allow_null=True)
    payment_terms = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = QuoteLineInputSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("Enter at least one price.")
        return lines


# ---------------------------------------------------------------- purchase orders

class POLineSerializer(_DocLineSerializer):
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=ZERO)
    required_qty = serializers.DecimalField(source="requirement_line.required_qty", max_digits=14, decimal_places=2, read_only=True, default=None)
    ordered_total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "requirement_line", "mr_no", "category", "description", "colour", "unit", "quantity",
                  "unit_price", "amount", "required_qty", "ordered_total"]
        read_only_fields = ["amount"]

    def get_ordered_total(self, obj):
        """All non-cancelled ordering of this requirement line, this PO included."""
        return ordered_of(obj.requirement_line) if obj.requirement_line_id else None


class PurchaseOrderSerializer(HistoryMixin, serializers.ModelSerializer):
    doc_type = "po"
    lines = POLineSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    supplier_email = serializers.CharField(source="supplier.email", read_only=True)
    supplier_address = serializers.SerializerMethodField()
    company_name = serializers.CharField(source="company.name", read_only=True)
    company_address = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    mr_no = serializers.CharField(source="requirement.mr_no", read_only=True, default=None)
    rfq_no = serializers.CharField(source="rfq.rfq_no", read_only=True, default=None)
    approved_by_name = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    currency = serializers.CharField(max_length=3, required=False)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "po_no", "company", "company_name", "company_address", "supplier", "supplier_name", "supplier_email",
            "supplier_address", "requirement", "mr_no", "rfq",
            "rfq_no", "order_date", "delivery_date", "currency", "payment_terms", "delivery_address", "notes",
            "status", "status_label", "approved_by_name", "approved_at", "sent_at", "cancel_reason", "total",
            "lines", "allowed_actions", "history", "created_at", "updated_at",
        ]
        read_only_fields = ["po_no", "company", "rfq", "status", "approved_at", "sent_at", "cancel_reason", "total",
                            "created_at", "updated_at"]

    def get_approved_by_name(self, obj):
        return _name(obj.approved_by)

    @staticmethod
    def _address(party):
        lines = [party.address, ", ".join(x for x in (party.city, party.country) if x)]
        if party.tax_id:
            lines.append(f"GSTIN {party.tax_id}")
        return "\n".join(x for x in lines if x)

    def get_supplier_address(self, obj):
        return self._address(obj.supplier)

    def get_company_address(self, obj):
        return self._address(obj.company)

    def get_allowed_actions(self, obj):
        return services.po_actions(obj, _user(self))

    def validate(self, attrs):
        if self.instance:
            services.ensure_draft(self.instance, "purchase order")
        supplier = attrs.get("supplier", getattr(self.instance, "supplier", None))
        if self.instance and supplier != self.instance.supplier and self.instance.rfq_id:
            raise serializers.ValidationError({"supplier": "This PO came from an RFQ award; the supplier cannot change."})
        req = attrs.get("requirement", getattr(self.instance, "requirement", None))
        if req and req.company_id != supplier.company_id:
            raise serializers.ValidationError({"requirement": "That requirement is for another company."})
        order_date = attrs.get("order_date", getattr(self.instance, "order_date", None))
        delivery = attrs.get("delivery_date", getattr(self.instance, "delivery_date", None))
        if delivery and order_date and delivery < order_date:
            raise serializers.ValidationError({"delivery_date": "Delivery can't be before the order date."})
        if "lines" in attrs:
            if not attrs["lines"]:
                raise serializers.ValidationError({"lines": "Add at least one line."})
            services.check_requirement_lines(attrs["lines"], supplier.company)
        if "currency" in attrs:
            attrs["currency"] = attrs["currency"].upper()
        return attrs

    def _save_lines(self, po, lines):
        if lines is not None:
            po.lines.all().delete()
            for i, line in enumerate(lines):
                PurchaseOrderLine.objects.create(order=po, position=i, **line)
        po.recalculate()

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        supplier = validated_data["supplier"]
        validated_data.setdefault("currency", supplier.company.currency or "INR")
        validated_data.setdefault("payment_terms", supplier.payment_terms)
        po = PurchaseOrder.objects.create(company=supplier.company, created_by=_user(self), **validated_data)
        self._save_lines(po, lines)
        services.log("po", po, "created", _user(self))
        return po

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        self._save_lines(instance, lines)
        return instance


class PurchaseOrderListSerializer(PurchaseOrderSerializer):
    class Meta(PurchaseOrderSerializer.Meta):
        fields = ["id", "po_no", "company", "supplier", "supplier_name", "mr_no", "rfq_no", "order_date",
                  "delivery_date", "currency", "total", "status", "status_label", "created_at"]
