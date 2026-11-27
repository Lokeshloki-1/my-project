from datetime import date as date_cls
from decimal import Decimal

from rest_framework import serializers

from apps.development.models import TechPack
from apps.merchandising.models import OrderConfirmation

from . import services
from .models import ActivityLog, ProductionEntry, ProductionLine, ProductionOrder


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class ProductionLineSerializer(serializers.ModelSerializer):
    efficiency_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("1"), max_value=Decimal("100"), required=False)

    class Meta:
        model = ProductionLine
        fields = ["id", "company", "code", "name", "operators", "working_minutes", "efficiency_pct", "is_active"]

    def validate(self, attrs):
        if self.instance and "company" in attrs and attrs["company"] != self.instance.company:
            raise serializers.ValidationError({"company": "The company of a line cannot be changed."})
        return attrs


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "action", "note", "user_name", "created_at"]

    def get_user_name(self, obj):
        return _name(obj.user)


class ProductionEntrySerializer(serializers.ModelSerializer):
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    line_name = serializers.CharField(source="line.name", read_only=True, default=None)
    entered_by_name = serializers.SerializerMethodField()
    quantity = serializers.IntegerField(min_value=0, required=False, default=0)
    rejected = serializers.IntegerField(min_value=0, required=False, default=0)
    sizes = serializers.DictField(child=serializers.IntegerField(min_value=0), required=False)

    class Meta:
        model = ProductionEntry
        fields = ["id", "production_order", "stage", "stage_label", "date", "sizes", "quantity", "rejected", "line",
                  "line_name", "lay_no", "fabric_used", "remarks", "entered_by_name", "created_at"]
        read_only_fields = ["production_order", "created_at"]

    def get_entered_by_name(self, obj):
        return _name(obj.entered_by)


class ProductionOrderSerializer(serializers.ModelSerializer):
    sizes = serializers.DictField(child=serializers.IntegerField(min_value=0))
    oc_no = serializers.CharField(source="order.oc_no", read_only=True)
    buyer_name = serializers.CharField(source="order.buyer.legal_name", read_only=True)
    ship_date = serializers.DateField(source="order.ship_date", read_only=True)
    order_line_quantity = serializers.IntegerField(source="order_line.quantity", read_only=True)
    style_name = serializers.CharField(source="order_line.description", read_only=True)
    line_name = serializers.CharField(source="line.name", read_only=True)
    tp_no = serializers.CharField(source="tech_pack.tp_no", read_only=True, default=None)
    production_approved = serializers.BooleanField(source="tech_pack.production_approved", read_only=True, default=False)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    size_order = serializers.SerializerMethodField()
    capacity = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    entries = ProductionEntrySerializer(many=True, read_only=True)
    materials = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    planned_end = serializers.DateField(required=False)
    smv = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0.5"))
    cut_allowance_pct = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("20"), required=False)

    class Meta:
        model = ProductionOrder
        fields = [
            "id", "wo_no", "company", "order", "oc_no", "buyer_name", "ship_date", "order_line", "order_line_quantity",
            "tech_pack", "tp_no", "production_approved", "style_no", "style_name", "colourway", "quantity", "sizes", "size_order",
            "line", "line_name", "smv", "planned_start", "planned_end", "cut_allowance_pct", "notes", "status",
            "status_label", "started_at", "completed_at", "close_reason", "capacity", "progress", "warnings",
            "allowed_actions", "entries", "materials", "history", "created_at", "updated_at",
        ]
        read_only_fields = ["wo_no", "company", "style_no", "status", "started_at", "completed_at", "close_reason",
                            "created_at", "updated_at"]

    def get_size_order(self, obj):
        return services.wo_sizes(obj)

    def get_capacity(self, obj):
        return services.capacity(obj.line, obj.smv, obj.quantity, obj.planned_start)

    def get_progress(self, obj):
        return services.totals(obj)

    def get_warnings(self, obj):
        return services.plan_warnings(obj) if obj.status in (ProductionOrder.Status.PLANNED, ProductionOrder.Status.IN_PROGRESS) else []

    def get_allowed_actions(self, obj):
        return services.wo_actions(obj, self.context["request"].user)

    def get_materials(self, obj):
        return services.material_status(obj)

    def get_history(self, obj):
        return ActivityLogSerializer(obj.logs.select_related("user"), many=True).data

    def validate(self, attrs):
        inst = self.instance
        if inst:
            if inst.status != ProductionOrder.Status.PLANNED:
                raise services.Conflict("Only planned work orders can be changed.")
            for f in ("order", "order_line"):
                if f in attrs and attrs[f] != getattr(inst, f):
                    raise serializers.ValidationError({f: "Plan a new work order for another order or style."})
        get = lambda f: attrs.get(f, getattr(inst, f, None))  # noqa: E731
        order, order_line, line = get("order"), get("order_line"), get("line")
        if order.status != OrderConfirmation.Status.CONFIRMED:
            raise serializers.ValidationError({"order": "Production is planned for confirmed orders."})
        if order_line.order_id != order.id:
            raise serializers.ValidationError({"order_line": "That style is not on this order."})
        if line.company_id != order.company_id or not line.is_active:
            raise serializers.ValidationError({"line": "Choose an active line of the order's company."})
        quantity, sizes = get("quantity"), {str(k): int(v) for k, v in (get("sizes") or {}).items() if int(v) > 0}
        if not sizes:
            raise serializers.ValidationError({"sizes": "Split the quantity by size."})
        if sum(sizes.values()) != quantity:
            raise serializers.ValidationError({"sizes": f"Sizes add up to {sum(sizes.values())}, not {quantity}."})
        attrs["sizes"] = sizes
        tp = get("tech_pack")
        if tp is None and "tech_pack" not in attrs:
            tp = (TechPack.objects.filter(buyer=order.buyer, style_no=order_line.style_no, status=TechPack.Status.RELEASED)
                  .order_by("-revision").first())
            attrs["tech_pack"] = tp
        if tp:
            if tp.style_no != order_line.style_no or tp.buyer_id != order.buyer_id:
                raise serializers.ValidationError({"tech_pack": "That tech pack is for another style."})
            unknown = [s for s in sizes if tp.sizes and s not in tp.sizes]
            if unknown:
                raise serializers.ValidationError({"sizes": f"Sizes not in the tech pack: {', '.join(unknown)}."})
        limit = order_line.quantity * (1 + services.ORDER_OVERPLAN_PCT / 100) - services.planned_for_line(order_line, exclude=inst)
        if quantity > limit:
            raise serializers.ValidationError({"quantity": f"Only {int(max(limit, 0))} more pcs of {order_line.style_no} can be planned "
                                                           f"(order {order_line.quantity} + {services.ORDER_OVERPLAN_PCT}%)."})
        start = get("planned_start")
        if not attrs.get("planned_end") and not (inst and "planned_start" not in attrs and "quantity" not in attrs and "line" not in attrs and "smv" not in attrs):
            attrs["planned_end"] = services.capacity(line, get("smv"), quantity, start)["suggested_end"] or start
        end = attrs.get("planned_end", getattr(inst, "planned_end", None))
        if end and start and end < start:
            raise serializers.ValidationError({"planned_end": "The end date can't be before the start."})
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        order, order_line = validated_data["order"], validated_data["order_line"]
        wo = ProductionOrder.objects.create(company=order.company, style_no=order_line.style_no, created_by=user, **validated_data)
        services.log(wo, "planned", user, f"{wo.quantity} pcs on {wo.line.name}, {wo.planned_start:%d %b}–{wo.planned_end:%d %b}")
        return wo

    def update(self, instance, validated_data):
        wo = super().update(instance, validated_data)
        services.log(wo, "replanned", self.context["request"].user, f"{wo.quantity} pcs on {wo.line.name}, {wo.planned_start:%d %b}–{wo.planned_end:%d %b}")
        return wo


class ProductionOrderListSerializer(ProductionOrderSerializer):
    class Meta(ProductionOrderSerializer.Meta):
        fields = ["id", "wo_no", "company", "order", "oc_no", "buyer_name", "ship_date", "style_no", "style_name", "colourway",
                  "quantity", "line", "line_name", "smv", "planned_start", "planned_end", "status", "status_label", "progress",
                  "production_approved"]


def parse_date(value, default=None):
    try:
        return date_cls.fromisoformat(value) if value else default
    except ValueError:
        raise serializers.ValidationError({"date": "Use YYYY-MM-DD."}) from None
