from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrReadOnly
from apps.buyers.services import Conflict
from apps.merchandising.models import OrderConfirmation

from . import services
from .models import ProductionEntry, ProductionLine, ProductionOrder
from .serializers import (
    ProductionEntrySerializer,
    ProductionLineSerializer,
    ProductionOrderListSerializer,
    ProductionOrderSerializer,
    parse_date,
)


class ProductionLineViewSet(viewsets.ModelViewSet):
    queryset = ProductionLine.objects.all()
    serializer_class = ProductionLineSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company", "is_active"]
    search_fields = ["code", "name"]

    def perform_destroy(self, instance):
        if instance.production_orders.exists():
            raise Conflict("This line has work orders. Mark it inactive instead.")
        instance.delete()


class ProductionOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                             mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = ProductionOrder.objects.select_related("order__buyer", "order_line", "line", "tech_pack").prefetch_related(
        Prefetch("entries", queryset=ProductionEntry.objects.select_related("line", "entered_by"))
    )
    filterset_fields = {"company": ["exact"], "order": ["exact"], "line": ["exact"], "status": ["exact", "in"],
                        "planned_start": ["lte", "gte"], "planned_end": ["lte", "gte"]}
    search_fields = ["wo_no", "style_no", "order__oc_no", "order__buyer__legal_name"]
    ordering_fields = ["planned_start", "planned_end", "created_at"]

    def get_serializer_class(self):
        return ProductionOrderListSerializer if self.action == "list" else ProductionOrderSerializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=obj.pk)
        return Response(ProductionOrderSerializer(fresh, context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._detail(s.save(), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        s = self.get_serializer(self.get_object(), data=request.data, partial=kwargs.pop("partial", False))
        s.is_valid(raise_exception=True)
        return self._detail(s.save())

    @action(detail=True, methods=["post"])
    def entries(self, request, pk=None):
        wo = self.get_object()
        s = ProductionEntrySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.add_entry(wo, request.user, dict(s.validated_data))
        return self._detail(wo, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._detail(services.complete_wo(self.get_object(), request.user, str(request.data.get("reason", "")).strip()))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_wo(self.get_object(), request.user, str(request.data.get("reason", "")).strip()))

    @action(detail=False, methods=["get"], url_path="order-lines")
    def order_lines(self, request):
        """Styles of a confirmed order with how much is already planned — for the planning form."""
        order = get_object_or_404(OrderConfirmation.objects.select_related("buyer"), pk=request.query_params.get("order"))
        return Response({"order": order.id, "oc_no": order.oc_no, "ship_date": order.ship_date, "status": order.status,
                         "company": order.company_id, "lines": services.order_lines_for_planning(order)})

    @action(detail=False, methods=["get"])
    def capacity(self, request):
        """Daily target and suggested end for a line / SMV / quantity / start (live while planning)."""
        line = get_object_or_404(ProductionLine, pk=request.query_params.get("line"))
        try:
            smv, qty = float(request.query_params.get("smv") or 0), int(request.query_params.get("quantity") or 0)
        except ValueError:
            smv, qty = 0, 0
        start = parse_date(request.query_params.get("start"), timezone.localdate())
        return Response(services.capacity(line, smv, qty, start) if smv > 0 and qty > 0 else {"daily_target": line.daily_target(smv) if smv > 0 else 0, "working_days": None, "suggested_end": None})

    @action(detail=False, methods=["get"])
    def daily(self, request):
        day = parse_date(request.query_params.get("date"), timezone.localdate())
        return Response(services.daily_report(day, request.query_params.get("company") or None))


class ProductionEntryViewSet(mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = ProductionEntry.objects.select_related("production_order", "line", "entered_by")
    serializer_class = ProductionEntrySerializer
    filterset_fields = {"production_order": ["exact"], "stage": ["exact"], "date": ["exact", "gte", "lte"], "line": ["exact"]}

    def destroy(self, request, *args, **kwargs):
        services.delete_entry(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
