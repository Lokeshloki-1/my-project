from django.db import transaction
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrReadOnly

from .models import StockLevel, StockMovement, Warehouse
from .serializers import (
    ManualMovementSerializer, StockLevelSerializer, StockMovementSerializer, TransferSerializer, WarehouseSerializer,
)
from .services import move_stock, transfer_stock


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.select_related("company")
    serializer_class = WarehouseSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company", "is_active"]
    search_fields = ["code", "name", "city"]


class StockLevelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Current stock per product per warehouse.
    ?low_stock=true shows products whose TOTAL stock (all warehouses) is at or below their reorder level.
    """

    queryset = StockLevel.objects.select_related("product", "warehouse")
    serializer_class = StockLevelSerializer
    filterset_fields = {"warehouse": ["exact"], "product": ["exact"], "warehouse__company": ["exact"]}
    search_fields = ["product__sku", "product__name", "warehouse__name"]
    ordering_fields = ["quantity", "product__name"]

    def get_queryset(self):
        product_total = (
            StockLevel.objects.filter(product=OuterRef("product")).values("product")
            .annotate(t=Sum("quantity")).values("t")
        )
        qs = super().get_queryset().annotate(
            product_total=Coalesce(Subquery(product_total), 0, output_field=DecimalField(max_digits=14, decimal_places=2))
        )
        if self.request.query_params.get("low_stock") in ("1", "true"):
            qs = qs.filter(product__reorder_level__gt=0, product_total__lte=F("product__reorder_level"))
        if self.request.query_params.get("hide_empty") in ("1", "true"):
            qs = qs.exclude(quantity=0)
        return qs


class StockMovementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The stock ledger. Entries are never edited or deleted — correct mistakes with an adjustment."""

    queryset = StockMovement.objects.select_related("product", "warehouse", "sales_order", "created_by")
    serializer_class = StockMovementSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = {
        "product": ["exact"], "warehouse": ["exact"], "movement_type": ["exact"],
        "sales_order": ["exact"], "created_at": ["date__gte", "date__lte"],
    }
    search_fields = ["product__sku", "product__name", "reference", "note", "sales_order__order_no"]

    def create(self, request):
        data = ManualMovementSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        sign = -1 if v["movement_type"] == "issue" else 1
        with transaction.atomic():
            movement = move_stock(
                product=v["product"], warehouse=v["warehouse"], quantity=sign * v["quantity"],
                movement_type=ManualMovementSerializer.TYPES[v["movement_type"]], user=request.user,
                unit_cost=v.get("unit_cost"), reference=v["reference"], note=v["note"],
            )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def transfer(self, request):
        data = TransferSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        with transaction.atomic():
            out, into = transfer_stock(
                product=v["product"], from_warehouse=v["from_warehouse"], to_warehouse=v["to_warehouse"],
                quantity=v["quantity"], user=request.user, reference=v["reference"], note=v["note"],
            )
        return Response(StockMovementSerializer([out, into], many=True).data, status=status.HTTP_201_CREATED)
