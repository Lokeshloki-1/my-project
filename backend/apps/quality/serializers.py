from rest_framework import serializers

from apps.production.models import ProductionLine, ProductionOrder

from . import services
from .models import CorrectiveAction, DefectType, FinalDefect, FinalInspection, InlineDefect, InlineInspection, Severity


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class DefectTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DefectType
        fields = ["id", "company", "code", "name", "category", "severity", "is_active"]


# ---------------------------------------------------------------- inline

class InlineDefectSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="defect_type.name", read_only=True)
    code = serializers.CharField(source="defect_type.code", read_only=True)
    category = serializers.CharField(source="defect_type.category", read_only=True)

    class Meta:
        model = InlineDefect
        fields = ["defect_type", "code", "name", "category", "count"]


class InlineInspectionSerializer(serializers.ModelSerializer):
    defects = InlineDefectSerializer(many=True, required=False)
    production_order = serializers.PrimaryKeyRelatedField(queryset=ProductionOrder.objects.all())
    line = serializers.PrimaryKeyRelatedField(queryset=ProductionLine.objects.all(), required=False)
    wo_no = serializers.CharField(source="production_order.wo_no", read_only=True)
    style_no = serializers.CharField(source="production_order.style_no", read_only=True)
    line_name = serializers.CharField(source="line.name", read_only=True)
    inspector_name = serializers.SerializerMethodField()
    capa_id = serializers.SerializerMethodField()

    class Meta:
        model = InlineInspection
        fields = ["id", "production_order", "wo_no", "style_no", "line", "line_name", "date", "operation", "operator",
                  "pieces_checked", "defective_pieces", "total_defects", "dhu", "result", "action_taken", "defects",
                  "inspector_name", "capa_id", "created_at"]
        read_only_fields = ["total_defects", "dhu", "result", "created_at"]

    def get_inspector_name(self, obj):
        return _name(obj.inspector)

    def get_capa_id(self, obj):
        return obj.corrective_action.id if hasattr(obj, "corrective_action") else None

    def create(self, validated_data):
        defects = validated_data.pop("defects", [])
        wo = validated_data.pop("production_order")
        line = validated_data.pop("line", None) or wo.line
        return services.create_inline(self.context["request"].user, wo, line, validated_data,
                                      [(d["defect_type"], d["count"]) for d in defects])


# ---------------------------------------------------------------- final

class FinalDefectSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="defect_type.name", read_only=True)
    code = serializers.CharField(source="defect_type.code", read_only=True)

    class Meta:
        model = FinalDefect
        fields = ["defect_type", "code", "name", "severity", "count"]


class FinalInspectionSerializer(serializers.ModelSerializer):
    defects = FinalDefectSerializer(many=True, required=False)
    wo_no = serializers.CharField(source="production_order.wo_no", read_only=True)
    style_no = serializers.CharField(source="production_order.style_no", read_only=True)
    oc_no = serializers.CharField(source="production_order.order.oc_no", read_only=True)
    buyer_name = serializers.CharField(source="production_order.order.buyer.legal_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    inspector_name = serializers.SerializerMethodField()
    finished_pcs = serializers.SerializerMethodField()
    checklist_items = serializers.SerializerMethodField()
    reinspection_id = serializers.SerializerMethodField()
    capa_id = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    aql_major = serializers.ChoiceField(choices=services.aql.AQL_CHOICES, required=False)
    aql_minor = serializers.ChoiceField(choices=services.aql.AQL_CHOICES, required=False)

    class Meta:
        model = FinalInspection
        fields = ["id", "fi_no", "company", "production_order", "wo_no", "style_no", "oc_no", "buyer_name", "round",
                  "previous", "reinspection_id", "inspection_date", "inspected_by_party", "lot_size", "finished_pcs",
                  "aql_major", "aql_minor", "code_letter", "sample_size", "accept_major", "accept_minor",
                  "critical_found", "major_found", "minor_found", "checklist", "checklist_items", "cartons_checked",
                  "remarks", "defects", "status", "status_label", "fail_reasons", "inspector_name", "completed_at",
                  "capa_id", "allowed_actions", "created_at"]
        read_only_fields = ["fi_no", "company", "round", "previous", "code_letter", "sample_size", "accept_major",
                            "accept_minor", "critical_found", "major_found", "minor_found", "status", "fail_reasons",
                            "completed_at", "created_at"]

    def get_inspector_name(self, obj):
        return _name(obj.inspector)

    def get_finished_pcs(self, obj):
        return services.offered_limit(obj.production_order)

    def get_checklist_items(self, obj):
        return [{"key": k, "label": label} for k, label in FinalInspection.CHECKLIST]

    def get_reinspection_id(self, obj):
        return obj.reinspection.id if hasattr(obj, "reinspection") else None

    def get_capa_id(self, obj):
        return obj.corrective_action.id if hasattr(obj, "corrective_action") else None

    def get_allowed_actions(self, obj):
        return services.final_actions(obj, self.context["request"].user)

    def validate(self, attrs):
        inst = self.instance
        if inst:
            if inst.status != FinalInspection.Status.DRAFT:
                raise services.Conflict("This inspection is completed and can't be changed.")
            if "production_order" in attrs and attrs["production_order"] != inst.production_order:
                raise serializers.ValidationError({"production_order": "Start a new inspection for another work order."})
        wo = attrs.get("production_order", getattr(inst, "production_order", None))
        if wo.status not in (ProductionOrder.Status.IN_PROGRESS, ProductionOrder.Status.COMPLETED):
            raise serializers.ValidationError({"production_order": "Final inspection is for work orders with finished pieces."})
        lot = attrs.get("lot_size", getattr(inst, "lot_size", None))
        finished = services.offered_limit(wo)
        if lot > finished:
            raise serializers.ValidationError({"lot_size": f"Only {finished} pieces are finished."})
        checklist = attrs.get("checklist")
        if checklist is not None:
            keys = {k for k, _ in FinalInspection.CHECKLIST}
            attrs["checklist"] = {k: v for k, v in checklist.items() if k in keys and v in (True, False)}
        attrs.update(services.build_plan(lot, attrs.get("aql_major", getattr(inst, "aql_major", "2.5")),
                                         attrs.get("aql_minor", getattr(inst, "aql_minor", "4.0"))))
        for d in attrs.get("defects", []):
            if d["severity"] not in Severity.values:
                raise serializers.ValidationError({"defects": "Unknown severity."})
        return attrs

    def create(self, validated_data):
        defects = validated_data.pop("defects", [])
        wo = validated_data["production_order"]
        fi = FinalInspection.objects.create(company=wo.company, inspector=self.context["request"].user, **validated_data)
        services.save_final_defects(fi, [(d["defect_type"], d["severity"], d["count"]) for d in defects])
        return fi

    def update(self, instance, validated_data):
        defects = validated_data.pop("defects", None)
        fi = super().update(instance, validated_data)
        if defects is not None:
            services.save_final_defects(fi, [(d["defect_type"], d["severity"], d["count"]) for d in defects])
        return fi


class FinalInspectionListSerializer(FinalInspectionSerializer):
    class Meta(FinalInspectionSerializer.Meta):
        fields = ["id", "fi_no", "production_order", "wo_no", "style_no", "oc_no", "buyer_name", "round", "inspection_date",
                  "inspected_by_party", "lot_size", "sample_size", "critical_found", "major_found", "minor_found",
                  "accept_major", "accept_minor", "status", "status_label"]


# ---------------------------------------------------------------- CAPA

class CorrectiveActionSerializer(serializers.ModelSerializer):
    wo_no = serializers.CharField(source="production_order.wo_no", read_only=True, default=None)
    style_no = serializers.CharField(source="production_order.style_no", read_only=True, default=None)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    closed_by_name = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = CorrectiveAction
        fields = ["id", "company", "source", "source_label", "inline_inspection", "final_inspection", "production_order",
                  "wo_no", "style_no", "problem", "root_cause", "action", "owner", "due_date", "status", "is_overdue",
                  "closed_by_name", "closed_at", "created_at"]
        read_only_fields = ["source", "inline_inspection", "final_inspection", "status", "closed_at", "created_at"]

    def get_closed_by_name(self, obj):
        return _name(obj.closed_by)

    def get_is_overdue(self, obj):
        from django.utils import timezone
        return obj.status == "open" and obj.due_date is not None and obj.due_date < timezone.localdate()

    def validate(self, attrs):
        if self.instance and self.instance.status == CorrectiveAction.Status.CLOSED:
            raise services.Conflict("A closed corrective action can't be changed.")
        wo = attrs.get("production_order")
        company = attrs.get("company", getattr(self.instance, "company", None))
        if wo and company and wo.company_id != company.id:
            raise serializers.ValidationError({"production_order": "That work order is for another company."})
        return attrs

    def create(self, validated_data):
        return CorrectiveAction.objects.create(source=CorrectiveAction.Source.OTHER, created_by=self.context["request"].user, **validated_data)
