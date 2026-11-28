from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.merchandising.models import OrderConfirmation

from . import services
from .models import ActivityLog, CartonGroup, ExportDocument, ExportShipment, PackingList


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "action", "note", "user_name", "created_at"]

    def get_user_name(self, obj):
        return _name(obj.user)


class CartonGroupSerializer(serializers.ModelSerializer):
    sizes = serializers.DictField(child=serializers.IntegerField(min_value=0))
    cartons = serializers.IntegerField(read_only=True)
    pcs_per_carton = serializers.IntegerField(read_only=True)
    total_pcs = serializers.IntegerField(read_only=True)
    cbm_per_carton = serializers.DecimalField(max_digits=10, decimal_places=4, read_only=True)
    wo_no = serializers.CharField(source="production_order.wo_no", read_only=True)
    net_weight = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))
    gross_weight = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))
    from_carton = serializers.IntegerField(min_value=1)
    to_carton = serializers.IntegerField(min_value=1)

    class Meta:
        model = CartonGroup
        fields = ["id", "production_order", "wo_no", "style_no", "colourway", "from_carton", "to_carton", "sizes", "net_weight",
                  "gross_weight", "length_cm", "width_cm", "height_cm", "cartons", "pcs_per_carton", "total_pcs", "cbm_per_carton"]
        read_only_fields = ["style_no"]

    def validate(self, attrs):
        if attrs["to_carton"] < attrs["from_carton"]:
            raise serializers.ValidationError("“To carton” must be at least “from carton”.")
        if attrs["gross_weight"] < attrs["net_weight"]:
            raise serializers.ValidationError("Gross weight can't be less than net weight.")
        return attrs


class PackingListSerializer(serializers.ModelSerializer):
    groups = CartonGroupSerializer(many=True, required=False)
    oc_no = serializers.CharField(source="order.oc_no", read_only=True)
    buyer_name = serializers.CharField(source="order.buyer.legal_name", read_only=True)
    buyer_po_no = serializers.CharField(source="order.buyer_po_no", read_only=True)
    shipment_no = serializers.CharField(source="shipment.shipment_no", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    finalized_by_name = serializers.SerializerMethodField()
    pack_status = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = PackingList
        fields = ["id", "pl_no", "company", "order", "oc_no", "buyer_name", "buyer_po_no", "shipment", "shipment_no", "pack_date",
                  "method", "shipping_marks", "notes", "status", "status_label", "finalized_by_name", "finalized_at",
                  "total_cartons", "total_pcs", "net_weight", "gross_weight", "cbm", "groups", "pack_status",
                  "allowed_actions", "history", "created_at", "updated_at"]
        read_only_fields = ["pl_no", "company", "shipment", "status", "finalized_at", "total_cartons", "total_pcs", "net_weight",
                            "gross_weight", "cbm", "created_at", "updated_at"]

    def get_finalized_by_name(self, obj):
        return _name(obj.finalized_by)

    def get_pack_status(self, obj):
        """Per work order of the order: finished, passed inspection, packed elsewhere, still packable."""
        exclude = obj if obj.status == PackingList.Status.DRAFT else None
        return [services.wo_pack_status(wo, exclude_list=exclude)
                for wo in obj.order.production_orders.exclude(status="cancelled").prefetch_related("entries")]

    def get_allowed_actions(self, obj):
        return services.packing_actions(obj, self.context["request"].user)

    def get_history(self, obj):
        return ActivityLogSerializer(services.history("packing_list", obj.pk), many=True).data

    def validate(self, attrs):
        inst = self.instance
        if inst:
            if inst.status != PackingList.Status.DRAFT:
                raise services.Conflict("This packing list is finalized. A manager can reopen it.")
            if "order" in attrs and attrs["order"] != inst.order:
                raise serializers.ValidationError({"order": "Make a new packing list for another order."})
        order = attrs.get("order", getattr(inst, "order", None))
        if order.status != OrderConfirmation.Status.CONFIRMED:
            raise serializers.ValidationError({"order": "Packing lists are made for confirmed orders."})
        if "groups" in attrs:
            services.check_groups(order, attrs["groups"], packing_list=inst)
        return attrs

    def _save_groups(self, pl, groups):
        if groups is None:
            return
        pl.groups.all().delete()
        for g in groups:
            wo = g["production_order"]
            CartonGroup.objects.create(packing_list=pl, style_no=wo.style_no, colourway=g.get("colourway") or wo.colourway,
                                       **{k: v for k, v in g.items() if k != "colourway"})
        pl.recalculate()

    @transaction.atomic
    def create(self, validated_data):
        groups = validated_data.pop("groups", [])
        order = validated_data["order"]
        user = self.context["request"].user
        if not validated_data.get("shipping_marks"):
            validated_data["shipping_marks"] = f"{order.buyer.legal_name}\nPO: {order.buyer_po_no}\nStyle: \nCarton no.: __ of __\nMade in India"
        pl = PackingList.objects.create(company=order.company, created_by=user, **validated_data)
        self._save_groups(pl, groups)
        services.log("packing_list", pl, "created", user)
        return pl

    @transaction.atomic
    def update(self, instance, validated_data):
        groups = validated_data.pop("groups", None)
        pl = super().update(instance, validated_data)
        self._save_groups(pl, groups)
        return pl


class PackingListListSerializer(PackingListSerializer):
    class Meta(PackingListSerializer.Meta):
        fields = ["id", "pl_no", "order", "oc_no", "buyer_name", "buyer_po_no", "shipment", "shipment_no", "pack_date", "status",
                  "status_label", "total_cartons", "total_pcs", "gross_weight", "cbm"]


class ExportDocumentSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_doc_type_display", read_only=True)
    generated = serializers.SerializerMethodField()

    class Meta:
        model = ExportDocument
        fields = ["id", "doc_type", "label", "generated", "number", "date", "status", "note", "updated_at"]
        read_only_fields = ["doc_type", "updated_at"]

    def get_generated(self, obj):
        return obj.doc_type in ExportDocument.GENERATED

    def validate(self, attrs):
        if self.instance.shipment.status == ExportShipment.Status.CANCELLED:
            raise services.Conflict("This shipment is cancelled.")
        return attrs


class ExportShipmentSerializer(serializers.ModelSerializer):
    packing_list_ids = serializers.PrimaryKeyRelatedField(source="packing_lists", many=True, queryset=PackingList.objects.all(), required=False)
    packing_lists = PackingListListSerializer(many=True, read_only=True)
    documents = ExportDocumentSerializer(many=True, read_only=True)
    oc_no = serializers.CharField(source="order.oc_no", read_only=True)
    buyer_name = serializers.CharField(source="order.buyer.legal_name", read_only=True)
    buyer_country = serializers.CharField(source="order.buyer.country", read_only=True)
    buyer_po_no = serializers.CharField(source="order.buyer_po_no", read_only=True)
    ship_date = serializers.DateField(source="order.ship_date", read_only=True)
    incoterm = serializers.CharField(source="order.incoterm", read_only=True)
    currency = serializers.CharField(source="order.currency", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    totals = serializers.SerializerMethodField()
    invoice = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    sales_invoice_id = serializers.SerializerMethodField()

    class Meta:
        model = ExportShipment
        fields = ["id", "shipment_no", "company", "order", "oc_no", "buyer_name", "buyer_country", "buyer_po_no", "ship_date",
                  "incoterm", "currency", "mode", "port_of_loading", "port_of_discharge", "final_destination", "forwarder",
                  "carrier", "vessel", "voyage", "container_type", "container_no", "seal_no", "etd", "eta", "on_board_date",
                  "delivered_date", "bl_no", "shipping_bill_no", "shipping_bill_date", "invoice_no", "invoice_date", "hs_codes",
                  "notes", "status", "status_label", "cancel_reason", "packing_list_ids", "packing_lists", "documents", "totals",
                  "invoice", "warnings", "allowed_actions", "history", "sales_invoice_id", "created_at", "updated_at"]
        read_only_fields = ["shipment_no", "company", "on_board_date", "delivered_date", "invoice_no", "status", "cancel_reason",
                            "created_at", "updated_at"]

    def get_totals(self, obj):
        return services.shipment_totals(obj)

    def get_invoice(self, obj):
        rows = services.invoice_lines(obj)
        return {"lines": rows, "total": sum((r["amount"] for r in rows), Decimal("0"))}

    def get_warnings(self, obj):
        w = []
        if obj.status in ("planned", "booked") and obj.etd and obj.order.ship_date and obj.etd > obj.order.ship_date:
            w.append(f"ETD {obj.etd:%d %b} is after the agreed shipment date {obj.order.ship_date:%d %b %Y}.")
        missing = [s for s in {g.style_no for pl in obj.packing_lists.all() for g in pl.groups.all()} if not obj.hs_codes.get(s)]
        if missing and obj.status != "cancelled":
            w.append(f"HS code missing for {', '.join(sorted(missing))} (needed on the invoice and shipping bill).")
        pending = [d.get_doc_type_display() for d in obj.documents.all() if d.status == "pending"]
        if obj.status in ("shipped", "delivered") and pending:
            w.append(f"Documents still pending: {', '.join(pending)}.")
        return w

    def get_allowed_actions(self, obj):
        return services.shipment_actions(obj, self.context["request"].user)

    def get_sales_invoice_id(self, obj):
        """The finance sales invoice raised for this shipment, if any."""
        return obj.export_invoice.id if hasattr(obj, "export_invoice") else None

    def get_history(self, obj):
        return ActivityLogSerializer(services.history("shipment", obj.pk), many=True).data

    def validate(self, attrs):
        inst = self.instance
        if inst:
            if inst.status not in ("planned", "booked"):
                allowed = {"notes", "hs_codes", "shipping_bill_date", "eta"}
                if set(attrs) - allowed:
                    raise services.Conflict("After shipping only notes, HS codes, ETA and the shipping bill date can change.")
            if "order" in attrs and attrs["order"] != inst.order:
                raise serializers.ValidationError({"order": "Make a new shipment for another order."})
        order = attrs.get("order", getattr(inst, "order", None))
        if order.status != OrderConfirmation.Status.CONFIRMED:
            raise serializers.ValidationError({"order": "Export shipments are for confirmed orders."})
        if "hs_codes" in attrs:
            attrs["hs_codes"] = {str(k): str(v).strip() for k, v in attrs["hs_codes"].items() if str(v).strip()}
        etd, eta = attrs.get("etd", getattr(inst, "etd", None)), attrs.get("eta", getattr(inst, "eta", None))
        if etd and eta and eta < etd:
            raise serializers.ValidationError({"eta": "ETA can't be before ETD."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lists = validated_data.pop("packing_lists", [])
        order = validated_data["order"]
        user = self.context["request"].user
        validated_data.setdefault("final_destination", order.buyer.country)
        validated_data.setdefault("port_of_loading", order.delivery_port or "Chennai, India")
        s = ExportShipment.objects.create(company=order.company, created_by=user, **validated_data)
        services.create_documents(s)
        services.attach_packing_lists(s, lists, user)
        services.log("shipment", s, "created", user)
        return s

    @transaction.atomic
    def update(self, instance, validated_data):
        lists = validated_data.pop("packing_lists", None)
        s = super().update(instance, validated_data)
        if lists is not None:
            services.attach_packing_lists(s, lists, self.context["request"].user)
        return s


class ExportShipmentListSerializer(ExportShipmentSerializer):
    class Meta(ExportShipmentSerializer.Meta):
        fields = ["id", "shipment_no", "order", "oc_no", "buyer_name", "buyer_country", "mode", "port_of_discharge", "vessel",
                  "etd", "eta", "on_board_date", "invoice_no", "status", "status_label", "totals"]
