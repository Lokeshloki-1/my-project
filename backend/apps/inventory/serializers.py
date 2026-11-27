from decimal import Decimal

from rest_framework import serializers

from apps.sales.models import Product

from .models import StockLevel, StockMovement, Warehouse


class WarehouseSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = ["id", "company", "company_name", "code", "name", "address", "city", "is_active"]


class StockLevelSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    reorder_level = serializers.DecimalField(source="product.reorder_level", max_digits=12, decimal_places=2, read_only=True)
    cost_price = serializers.DecimalField(source="product.cost_price", max_digits=12, decimal_places=2, read_only=True)
    stock_value = serializers.SerializerMethodField()
    product_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, default=None)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = StockLevel
        fields = [
            "id", "product", "sku", "product_name", "warehouse", "warehouse_name", "quantity", "product_total",
            "reorder_level", "is_low_stock", "cost_price", "stock_value", "updated_at",
        ]

    def get_is_low_stock(self, obj):
        total = getattr(obj, "product_total", None)
        return total is not None and obj.product.reorder_level > 0 and total <= obj.product.reorder_level

    def get_stock_value(self, obj):
        return str((obj.quantity * obj.product.cost_price).quantize(Decimal("0.01")))


class StockMovementSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    order_no = serializers.CharField(source="sales_order.order_no", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "sku", "product_name", "warehouse", "warehouse_name", "movement_type", "type_label",
            "quantity", "balance_after", "unit_cost", "sales_order", "order_no", "reference", "note",
            "created_by_name", "created_at",
        ]


class ManualMovementSerializer(serializers.Serializer):
    """Input for receiving, issuing or adjusting stock by hand."""

    TYPES = {
        "receipt": StockMovement.Type.RECEIPT,
        "issue": StockMovement.Type.ISSUE,
        "adjustment": StockMovement.Type.ADJUSTMENT,
    }
    movement_type = serializers.ChoiceField(choices=list(TYPES))
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    # receipt / issue: a positive amount. adjustment: + or - (e.g. -3 after a stock count found 3 missing).
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        qty, kind = attrs["quantity"], attrs["movement_type"]
        if qty == 0:
            raise serializers.ValidationError({"quantity": "Cannot be zero."})
        if kind in ("receipt", "issue") and qty < 0:
            raise serializers.ValidationError({"quantity": "Enter a positive quantity."})
        if kind == "adjustment" and not attrs["note"].strip():
            raise serializers.ValidationError({"note": "Give a reason for the adjustment."})
        return attrs


class TransferSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    from_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    to_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
