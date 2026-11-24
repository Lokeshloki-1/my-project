from rest_framework import serializers

from .models import Shipment


class ShipmentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    sales_order_no = serializers.CharField(source="sales_order.order_no", read_only=True, default=None)
    cif_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    margin = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id", "shipment_no", "incoterm", "company", "company_name", "sales_order", "sales_order_no",
            "customer", "customer_name", "mode", "carrier", "tracking_no",
            "origin_country", "destination_country", "destination_address",
            "ship_date", "expected_delivery", "delivered_date", "status", "currency",
            "goods_value", "freight_cost", "insurance_cost", "customs_duty_rate", "import_vat_rate",
            "other_charges", "invoice_value",
            "cif_value", "customs_duty", "import_vat", "landed_cost", "margin",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "shipment_no", "incoterm", "customs_duty", "import_vat", "landed_cost", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        get = lambda f: attrs.get(f, getattr(self.instance, f, None))  # noqa: E731
        company, customer, order = get("company"), get("customer"), get("sales_order")
        if customer and customer.company_id != company.id:
            raise serializers.ValidationError({"customer": "Customer belongs to a different company."})
        if order and order.company_id != company.id:
            raise serializers.ValidationError({"sales_order": "Sales order belongs to a different company."})
        if order and customer and order.customer_id != customer.id:
            raise serializers.ValidationError({"sales_order": "Sales order is for a different customer."})
        if get("status") == Shipment.Status.DELIVERED and not get("delivered_date"):
            raise serializers.ValidationError({"delivered_date": "Set the delivered date when marking delivered."})
        ship, eta = get("ship_date"), get("expected_delivery")
        if ship and eta and eta < ship:
            raise serializers.ValidationError({"expected_delivery": "Cannot be before the ship date."})
        return attrs


class LandedCostQuoteSerializer(serializers.Serializer):
    """Input for the 'quote' calculator — nothing is saved."""

    goods_value = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    freight_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=0)
    insurance_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=0)
    customs_duty_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0)
    import_vat_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0)
    other_charges = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=0)
