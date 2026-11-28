from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers

from apps.buyers.services import Conflict

from . import services
from .models import ActivityLog, BOMItem, Measurement, Sample, SampleMeasurement, TechPack


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


def _clean_text_list(values, label):
    cleaned = []
    for v in values:
        v = str(v).strip()
        if v and v not in cleaned:
            cleaned.append(v)
    if len(cleaned) > 30:
        raise serializers.ValidationError(f"Too many {label}.")
    return cleaned


# ---------------------------------------------------------------- tech packs

class MeasurementSerializer(serializers.ModelSerializer):
    tolerance = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0"), required=False)

    class Meta:
        model = Measurement
        fields = ["id", "code", "point", "tolerance", "values"]

    def validate_values(self, values):
        if not isinstance(values, dict):
            raise serializers.ValidationError("Give one value per size.")
        cleaned = {}
        for size, value in values.items():
            if value in (None, ""):
                continue
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                raise serializers.ValidationError(f"“{value}” for size {size} is not a number.") from None
            if number < 0:
                raise serializers.ValidationError(f"Size {size} can't be negative.")
            cleaned[str(size)] = str(number)
        return cleaned


class BOMItemSerializer(serializers.ModelSerializer):
    consumption = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"), required=False, allow_null=True)

    class Meta:
        model = BOMItem
        fields = ["id", "category", "description", "supplier", "colour", "placement", "consumption", "unit"]


class TechPackSerializer(serializers.ModelSerializer):
    measurements = MeasurementSerializer(many=True, required=False)
    bom = BOMItemSerializer(many=True, required=False)
    colourways = serializers.ListField(child=serializers.CharField(max_length=100), required=False)
    sizes = serializers.ListField(child=serializers.CharField(max_length=20), required=False)
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    cost_no = serializers.CharField(source="cost_sheet.cost_no", read_only=True, default=None)
    released_by_name = serializers.SerializerMethodField()
    next_revision_id = serializers.SerializerMethodField()
    sample_count = serializers.SerializerMethodField()
    missing_for_release = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = TechPack
        fields = [
            "id", "tp_no", "revision", "previous", "next_revision_id", "company", "buyer", "buyer_name",
            "style_no", "style_name", "season", "category", "description", "fabric_composition", "gsm",
            "colourways", "sizes", "base_size", "construction", "wash_care", "packing", "cost_sheet", "cost_no",
            "status", "status_label", "released_by_name", "released_at", "production_approved",
            "production_approved_at", "sample_count", "measurements", "bom", "missing_for_release",
            "allowed_actions", "history", "created_at", "updated_at",
        ]
        read_only_fields = [
            "tp_no", "revision", "previous", "company", "status", "released_at", "production_approved",
            "production_approved_at", "created_at", "updated_at",
        ]

    def get_released_by_name(self, obj):
        return _name(obj.released_by)

    def get_next_revision_id(self, obj):
        nxt = getattr(obj, "next_revision", None) if hasattr(obj, "next_revision") else None
        return nxt.id if nxt else None

    def get_sample_count(self, obj):
        return obj.samples.count()

    def get_missing_for_release(self, obj):
        return services.missing_for_release(obj) if obj.status == TechPack.Status.DRAFT else []

    def get_allowed_actions(self, obj):
        return services.tech_pack_actions(obj, _user(self))

    def get_history(self, obj):
        return ActivityLogSerializer(services.history("tech_pack", obj.pk), many=True).data

    def validate(self, attrs):
        if self.instance:
            if self.instance.status != TechPack.Status.DRAFT:
                raise Conflict(
                    f"This tech pack is {self.instance.get_status_display().lower()}. Make a new revision to change it."
                )
            if "buyer" in attrs and attrs["buyer"] != self.instance.buyer:
                raise serializers.ValidationError({"buyer": "The buyer of a tech pack cannot be changed."})
        buyer = attrs.get("buyer", getattr(self.instance, "buyer", None))
        services.require_active_buyer(buyer)
        sheet = attrs.get("cost_sheet")
        if sheet and sheet.buyer_id != buyer.id:
            raise serializers.ValidationError({"cost_sheet": "That cost sheet is for another buyer."})
        if "sizes" in attrs:
            attrs["sizes"] = _clean_text_list(attrs["sizes"], "sizes")
        if "colourways" in attrs:
            attrs["colourways"] = _clean_text_list(attrs["colourways"], "colourways")
        sizes = attrs.get("sizes", getattr(self.instance, "sizes", []))
        base = attrs.get("base_size", getattr(self.instance, "base_size", ""))
        if base and sizes and base not in sizes:
            raise serializers.ValidationError({"base_size": "The base size must be one of the sizes."})
        for m in attrs.get("measurements", []):
            extra = [s for s in m.get("values", {}) if s not in sizes]
            if extra:
                raise serializers.ValidationError({"measurements": f"“{m['point']}” has values for unknown sizes: {', '.join(extra)}."})
        return attrs

    def _save_children(self, tp, measurements, bom):
        if measurements is not None:
            tp.measurements.all().delete()
            Measurement.objects.bulk_create([Measurement(tech_pack=tp, position=i, **m) for i, m in enumerate(measurements)])
        if bom is not None:
            tp.bom.all().delete()
            BOMItem.objects.bulk_create([BOMItem(tech_pack=tp, position=i, **b) for i, b in enumerate(bom)])

    @transaction.atomic
    def create(self, validated_data):
        measurements = validated_data.pop("measurements", [])
        bom = validated_data.pop("bom", [])
        buyer = validated_data["buyer"]
        tp = TechPack.objects.create(company=buyer.company, created_by=_user(self), **validated_data)
        self._save_children(tp, measurements, bom)
        services.log("tech_pack", tp, "created", _user(self))
        return tp

    @transaction.atomic
    def update(self, instance, validated_data):
        measurements = validated_data.pop("measurements", None)
        bom = validated_data.pop("bom", None)
        instance = super().update(instance, validated_data)
        self._save_children(instance, measurements, bom)
        return instance


class TechPackListSerializer(TechPackSerializer):
    class Meta(TechPackSerializer.Meta):
        fields = [
            "id", "tp_no", "revision", "buyer", "buyer_name", "style_no", "style_name", "season", "category",
            "status", "status_label", "production_approved", "sample_count", "updated_at",
        ]


# ---------------------------------------------------------------- samples

class SampleMeasurementSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="measurement.code", read_only=True)
    point = serializers.CharField(source="measurement.point", read_only=True)
    deviation = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    within_tolerance = serializers.BooleanField(read_only=True)

    class Meta:
        model = SampleMeasurement
        fields = ["id", "measurement", "code", "point", "spec", "tolerance", "actual", "deviation", "within_tolerance"]


class SampleSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source="buyer.legal_name", read_only=True)
    tp_no = serializers.CharField(source="tech_pack.tp_no", read_only=True)
    tp_revision = serializers.IntegerField(source="tech_pack.revision", read_only=True)
    style_no = serializers.CharField(source="tech_pack.style_no", read_only=True)
    style_name = serializers.CharField(source="tech_pack.style_name", read_only=True)
    type_label = serializers.CharField(source="get_sample_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    previous_no = serializers.CharField(source="previous.sample_no", read_only=True, default=None)
    resubmission_id = serializers.SerializerMethodField()
    is_late = serializers.SerializerMethodField()
    measurements = SampleMeasurementSerializer(many=True, read_only=True)
    measurement_summary = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    size = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = Sample
        fields = [
            "id", "sample_no", "company", "tech_pack", "tp_no", "tp_revision", "buyer", "buyer_name", "style_no",
            "style_name", "sample_type", "type_label", "round", "previous", "previous_no", "resubmission_id",
            "colourway", "size", "quantity", "requested_on", "due_date", "instructions", "status", "status_label",
            "is_late", "courier", "tracking_no", "sent_on", "buyer_comments", "decided_on", "measurements",
            "measurement_summary", "allowed_actions", "history", "created_at", "updated_at",
        ]
        read_only_fields = [
            "sample_no", "company", "buyer", "round", "previous", "status", "courier", "tracking_no", "sent_on",
            "buyer_comments", "decided_on", "created_at", "updated_at",
        ]

    def get_resubmission_id(self, obj):
        return obj.resubmission.id if hasattr(obj, "resubmission") else None

    def get_is_late(self, obj):
        from django.utils import timezone
        return bool(obj.due_date and obj.status in (Sample.Status.REQUESTED, Sample.Status.IN_PROGRESS, Sample.Status.READY)
                    and obj.due_date < timezone.localdate())

    def get_measurement_summary(self, obj):
        return services.measurement_summary(obj)

    def get_allowed_actions(self, obj):
        return services.sample_actions(obj, _user(self))

    def get_history(self, obj):
        return ActivityLogSerializer(services.history("sample", obj.pk), many=True).data

    def validate(self, attrs):
        if self.instance:
            if self.instance.status not in (Sample.Status.REQUESTED, Sample.Status.IN_PROGRESS, Sample.Status.READY):
                raise Conflict("This sample has been sent to the buyer and can no longer be edited.")
            if "tech_pack" in attrs and attrs["tech_pack"] != self.instance.tech_pack:
                raise serializers.ValidationError({"tech_pack": "The tech pack of a sample cannot be changed."})
            if "sample_type" in attrs and attrs["sample_type"] != self.instance.sample_type:
                raise serializers.ValidationError({"sample_type": "Request a new sample for another type."})
        tp = attrs.get("tech_pack", getattr(self.instance, "tech_pack", None))
        if not self.instance and tp.status != TechPack.Status.RELEASED:
            raise serializers.ValidationError({"tech_pack": "Samples can only be requested from a released tech pack."})
        size = attrs.get("size")
        if size and tp.sizes and size not in tp.sizes:
            raise serializers.ValidationError({"size": f"Size must be one of {', '.join(tp.sizes)}."})
        colour = attrs.get("colourway")
        if colour and tp.colourways and colour not in tp.colourways:
            raise serializers.ValidationError({"colourway": f"Colourway must be one of {', '.join(tp.colourways)}."})
        due, requested = attrs.get("due_date"), attrs.get("requested_on", getattr(self.instance, "requested_on", None))
        if due and requested and due < requested:
            raise serializers.ValidationError({"due_date": "The due date can't be before the request date."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        tp = validated_data["tech_pack"]
        validated_data.setdefault("size", tp.base_size)
        sample = Sample.objects.create(
            company=tp.company, buyer=tp.buyer, round=services.next_round(tp, validated_data["sample_type"]),
            created_by=_user(self), **validated_data,
        )
        services.log("sample", sample, "requested", _user(self), f"{sample.get_sample_type_display()}, round {sample.round}")
        return sample


class SampleListSerializer(SampleSerializer):
    class Meta(SampleSerializer.Meta):
        fields = [
            "id", "sample_no", "tech_pack", "tp_no", "buyer", "buyer_name", "style_no", "style_name", "sample_type",
            "type_label", "round", "colourway", "size", "requested_on", "due_date", "status", "status_label", "is_late",
            "sent_on", "decided_on",
        ]
