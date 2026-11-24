from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import Customer, Product, SalesOrder, SalesOrderItem


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "company", "name", "email", "phone", "tax_id", "address", "city", "country", "created_at"]
        read_only_fields = ["created_at"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "company", "sku", "name", "hs_code", "unit_price", "tax_rate", "is_active"]


class SalesOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    # Price and tax default to the product's current values when not sent.
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = SalesOrderItem
        fields = ["id", "product", "product_name", "quantity", "unit_price", "tax_rate", "line_total"]


class SalesOrderSerializer(serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    salesperson_name = serializers.CharField(source="salesperson.full_name", read_only=True, default=None)
    company_name = serializers.CharField(source="company.name", read_only=True)
    invoice_id = serializers.IntegerField(source="invoice.id", read_only=True, default=None)
    invoice_no = serializers.CharField(source="invoice.invoice_no", read_only=True, default=None)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "order_no", "company", "company_name", "customer", "customer_name",
            "salesperson", "salesperson_name", "order_date", "status", "notes",
            "items", "subtotal", "tax_amount", "total", "invoice_id", "invoice_no", "created_at", "updated_at",
        ]
        read_only_fields = ["order_no", "subtotal", "tax_amount", "total", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance and hasattr(self.instance, "invoice"):
            raise serializers.ValidationError(
                f"Order is locked because invoice {self.instance.invoice.invoice_no} was issued for it."
            )
        status = attrs.get("status")
        current = getattr(self.instance, "status", None)
        if status in (SalesOrder.Status.INVOICED, SalesOrder.Status.PAID) and status != current:
            raise serializers.ValidationError(
                {"status": "Invoiced and paid are set automatically by creating an invoice and recording payments."}
            )
        company = attrs.get("company", getattr(self.instance, "company", None))
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        salesperson = attrs.get("salesperson", getattr(self.instance, "salesperson", None))
        if customer and customer.company_id != company.id:
            raise serializers.ValidationError({"customer": "Customer belongs to a different company."})
        if salesperson and salesperson.company_id != company.id:
            raise serializers.ValidationError({"salesperson": "Salesperson belongs to a different company."})
        items = attrs.get("items")
        if items is not None:
            if not items:
                raise serializers.ValidationError({"items": "An order needs at least one item."})
            for item in items:
                if item["product"].company_id != company.id:
                    raise serializers.ValidationError({"items": f"Product {item['product']} belongs to a different company."})
        return attrs

    def _save_items(self, order, items):
        order.items.all().delete()
        SalesOrderItem.objects.bulk_create([
            SalesOrderItem(
                order=order,
                product=item["product"],
                quantity=item["quantity"],
                unit_price=item.get("unit_price", item["product"].unit_price),
                tax_rate=item.get("tax_rate", item["product"].tax_rate),
            )
            for item in items
        ])
        order.recalculate_totals()

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items")
        order = SalesOrder.objects.create(**validated_data)
        self._save_items(order, items)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if items is not None:
            self._save_items(instance, items)
        return instance
