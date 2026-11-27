from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.inventory.models import Warehouse

from . import services
from .models import ActivityLog, GoodsReceipt, GoodsReceiptLine, Material, MaterialAllocation, MaterialMovement, MaterialStock


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


class MaterialSerializer(serializers.ModelSerializer):
    on_hand = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=0)
    allocated = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=0)
    value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True, default=0)
    is_low = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ["id", "code", "company", "category", "description", "colour", "unit", "reorder_level",
                  "on_hand", "allocated", "value", "is_low", "created_at"]
        read_only_fields = ["code", "created_at"]

    def get_is_low(self, obj):
        on_hand = getattr(obj, "on_hand", None) or 0
        return obj.reorder_level > 0 and on_hand <= obj.reorder_level

    def validate(self, attrs):
        if self.instance:
            for f in ("company", "category", "description", "colour", "unit"):
                if f in attrs and attrs[f] != getattr(self.instance, f) and self.instance.movements.exists():
                    raise serializers.ValidationError({f: "This material has stock movements; only the reorder level can change."})
        return attrs


class MaterialStockSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="material.code", read_only=True)
    category = serializers.CharField(source="material.category", read_only=True)
    description = serializers.CharField(source="material.description", read_only=True)
    colour = serializers.CharField(source="material.colour", read_only=True)
    unit = serializers.CharField(source="material.unit", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    available = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    average_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = MaterialStock
        fields = ["id", "material", "code", "category", "description", "colour", "unit", "warehouse", "warehouse_name",
                  "on_hand", "allocated", "available", "average_cost", "value", "updated_at"]


class MaterialMovementSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.__str__", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = MaterialMovement
        fields = ["id", "material", "material_name", "warehouse", "warehouse_name", "movement_type", "type_label",
                  "quantity", "balance_after", "unit_cost", "reference", "note", "user_name", "created_at"]

    def get_user_name(self, obj):
        return _name(obj.created_by)


class AdjustSerializer(serializers.Serializer):
    material = serializers.PrimaryKeyRelatedField(queryset=Material.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    new_quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    reason = serializers.CharField(max_length=300)


# ---------------------------------------------------------------- goods receipts

class GRNLineSerializer(serializers.ModelSerializer):
    received_qty = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField(source="po_line.description", read_only=True)
    category = serializers.CharField(source="po_line.category", read_only=True)
    colour = serializers.CharField(source="po_line.colour", read_only=True)
    unit = serializers.CharField(source="po_line.unit", read_only=True)
    ordered_qty = serializers.DecimalField(source="po_line.quantity", max_digits=14, decimal_places=2, read_only=True)
    unit_price = serializers.DecimalField(source="po_line.unit_price", max_digits=12, decimal_places=2, read_only=True)
    material_code = serializers.CharField(source="material.code", read_only=True)
    result_label = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = GoodsReceiptLine
        fields = ["id", "po_line", "description", "category", "colour", "unit", "ordered_qty", "unit_price",
                  "material", "material_code", "received_qty", "lot_no", "rolls", "accepted_qty", "rejected_qty",
                  "result", "result_label", "remarks"]
        read_only_fields = ["material", "accepted_qty", "rejected_qty", "result", "remarks"]


class GoodsReceiptSerializer(serializers.ModelSerializer):
    lines = GRNLineSerializer(many=True)
    po_no = serializers.CharField(source="purchase_order.po_no", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    inspected_by_name = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = ["id", "grn_no", "company", "purchase_order", "po_no", "supplier", "supplier_name", "warehouse",
                  "warehouse_name", "received_on", "challan_no", "invoice_no", "vehicle_no", "notes", "status",
                  "status_label", "submitted_at", "inspected_by_name", "inspected_at", "inspection_notes", "totals",
                  "lines", "allowed_actions", "history", "created_at", "updated_at"]
        read_only_fields = ["grn_no", "company", "supplier", "status", "submitted_at", "inspected_at",
                            "inspection_notes", "created_at", "updated_at"]

    def get_inspected_by_name(self, obj):
        return _name(obj.inspected_by)

    def get_totals(self, obj):
        lines = list(obj.lines.all())
        return {k: sum((getattr(line, f"{k}_qty") for line in lines), Decimal("0")) for k in ("received", "accepted", "rejected")}

    def get_allowed_actions(self, obj):
        return services.grn_actions(obj, _user(self))

    def get_history(self, obj):
        return ActivityLogSerializer(services.history("grn", obj.pk), many=True).data

    def validate(self, attrs):
        if self.instance:
            if self.instance.status != GoodsReceipt.Status.DRAFT:
                raise services.Conflict("This goods receipt has been submitted and can no longer be edited.")
            if "purchase_order" in attrs and attrs["purchase_order"] != self.instance.purchase_order:
                raise serializers.ValidationError({"purchase_order": "The PO of a goods receipt cannot be changed."})
        po = attrs.get("purchase_order", getattr(self.instance, "purchase_order", None))
        services.check_po(po)
        warehouse = attrs.get("warehouse", getattr(self.instance, "warehouse", None))
        if warehouse.company_id != po.company_id or not warehouse.is_active:
            raise serializers.ValidationError({"warehouse": "Choose an active warehouse of the PO's company."})
        if "lines" in attrs:
            if not attrs["lines"]:
                raise serializers.ValidationError({"lines": "Enter at least one line."})
            ids = [line["po_line"].id for line in attrs["lines"]]
            if len(ids) != len(set(ids)):
                raise serializers.ValidationError({"lines": "Each PO line can appear once per receipt."})
            services.check_receipt_lines(self.instance, po, attrs["lines"])
        return attrs

    def _save_lines(self, grn, lines):
        if lines is None:
            return
        grn.lines.all().delete()
        for i, line in enumerate(lines):
            pl = line["po_line"]
            material = services.material_for(grn.company, pl.category, pl.description, pl.colour, pl.unit)
            GoodsReceiptLine.objects.create(receipt=grn, material=material, position=i, **line)

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        po = validated_data["purchase_order"]
        grn = GoodsReceipt.objects.create(company=po.company, supplier=po.supplier, created_by=_user(self), **validated_data)
        self._save_lines(grn, lines)
        services.log("grn", grn, "created", _user(self), f"Against {po.po_no}")
        return grn

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        self._save_lines(instance, lines)
        return instance


class GoodsReceiptListSerializer(GoodsReceiptSerializer):
    class Meta(GoodsReceiptSerializer.Meta):
        fields = ["id", "grn_no", "purchase_order", "po_no", "supplier_name", "warehouse_name", "received_on",
                  "challan_no", "status", "status_label", "totals", "created_at"]


class InspectionSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------- allocations

class AllocationSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.__str__", read_only=True)
    material_code = serializers.CharField(source="material.code", read_only=True)
    unit = serializers.CharField(source="material.unit", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    oc_no = serializers.CharField(source="order.oc_no", read_only=True)
    buyer_name = serializers.CharField(source="order.buyer.legal_name", read_only=True)
    remaining = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = MaterialAllocation
        fields = ["id", "material", "material_name", "material_code", "unit", "warehouse", "warehouse_name", "order",
                  "oc_no", "buyer_name", "requirement_line", "quantity", "issued_qty", "released_qty", "remaining",
                  "status", "status_label", "note", "created_by_name", "created_at"]
        read_only_fields = ["issued_qty", "released_qty", "status", "created_at"]

    def get_created_by_name(self, obj):
        return _name(obj.created_by)

    def create(self, validated_data):
        return services.allocate(
            validated_data["order"], validated_data["material"], validated_data["warehouse"], validated_data["quantity"],
            _user(self), validated_data.get("requirement_line"), validated_data.get("note", ""),
        )
