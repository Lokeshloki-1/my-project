from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrReadOnly
from apps.buyers.services import Conflict
from apps.inventory.models import Warehouse
from apps.procurement.models import MaterialRequirement, PurchaseOrder

from . import services
from .models import GoodsReceipt, Material, MaterialAllocation, MaterialMovement, MaterialStock
from .serializers import (
    AdjustSerializer,
    AllocationSerializer,
    GoodsReceiptListSerializer,
    GoodsReceiptSerializer,
    InspectionSerializer,
    MaterialMovementSerializer,
    MaterialSerializer,
    MaterialStockSerializer,
)

_DEC = DecimalField(max_digits=16, decimal_places=2)


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.annotate(
        on_hand=Coalesce(Sum("stock__on_hand"), Value(0), output_field=_DEC),
        allocated=Coalesce(Sum("stock__allocated"), Value(0), output_field=_DEC),
        value=Coalesce(Sum("stock__value"), Value(0), output_field=_DEC),
    )
    serializer_class = MaterialSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company", "category"]
    search_fields = ["code", "description", "colour"]

    def perform_destroy(self, instance):
        if instance.movements.exists() or instance.grn_lines.exists():
            raise Conflict("This material has receipts or movements and cannot be deleted.")
        instance.delete()


class MaterialStockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialStock.objects.select_related("material", "warehouse")
    serializer_class = MaterialStockSerializer
    filterset_fields = {"warehouse": ["exact"], "material": ["exact"], "material__category": ["exact"],
                        "material__company": ["exact"], "on_hand": ["gt"]}
    search_fields = ["material__code", "material__description", "material__colour"]
    ordering_fields = ["on_hand", "value", "updated_at"]

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        data = AdjustSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        mv = services.adjust_stock(d["material"], d["warehouse"], d["new_quantity"], d["reason"].strip(), request.user)
        return Response(MaterialMovementSerializer(mv).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(services.stock_summary(request.query_params.get("company") or None))


class MaterialMovementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialMovement.objects.select_related("material", "warehouse", "created_by")
    serializer_class = MaterialMovementSerializer
    filterset_fields = {"material": ["exact"], "warehouse": ["exact"], "movement_type": ["exact"], "created_at": ["gte", "lte"]}
    search_fields = ["reference", "note", "material__description"]


class GoodsReceiptViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                          mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = GoodsReceipt.objects.select_related("purchase_order", "supplier", "warehouse", "inspected_by").prefetch_related(
        "lines__po_line", "lines__material"
    )
    filterset_fields = ["company", "status", "purchase_order", "supplier", "warehouse"]
    search_fields = ["grn_no", "challan_no", "invoice_no", "supplier__name", "purchase_order__po_no"]
    ordering_fields = ["received_on", "created_at"]

    def get_serializer_class(self):
        return GoodsReceiptListSerializer if self.action == "list" else GoodsReceiptSerializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=obj.pk)
        return Response(GoodsReceiptSerializer(fresh, context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._detail(s.save(), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        s = self.get_serializer(self.get_object(), data=request.data, partial=kwargs.pop("partial", False))
        s.is_valid(raise_exception=True)
        return self._detail(s.save())

    def perform_destroy(self, instance):
        if instance.status != GoodsReceipt.Status.DRAFT:
            raise Conflict("Only draft goods receipts can be deleted.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def receivable(self, request):
        """Lines of a sent PO with ordered / received / open quantity."""
        po = get_object_or_404(PurchaseOrder.objects.prefetch_related("lines"), pk=request.query_params.get("purchase_order"))
        return Response({"purchase_order": po.id, "po_no": po.po_no, "supplier": po.supplier.name, "status": po.status,
                         "company": po.company_id, "lines": services.receivable_lines(po)})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._detail(services.submit_grn(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def inspect(self, request, pk=None):
        data = InspectionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        grn = services.inspect_grn(self.get_object(), request.user, data.validated_data["results"], data.validated_data["notes"].strip())
        return self._detail(grn)


class AllocationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = MaterialAllocation.objects.select_related("material", "warehouse", "order__buyer", "created_by")
    serializer_class = AllocationSerializer
    filterset_fields = ["company", "status", "order", "material", "warehouse", "requirement_line"]
    search_fields = ["order__oc_no", "material__description", "material__code"]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        alloc = s.save()
        return Response(self.get_serializer(self.get_queryset().get(pk=alloc.pk)).data, status=status.HTTP_201_CREATED)

    def _one(self, alloc):
        return Response(self.get_serializer(self.get_queryset().get(pk=alloc.pk)).data)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        return self._one(services.release_allocation(self.get_object(), request.user, request.data.get("quantity")))

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        return self._one(services.issue_allocation(self.get_object(), request.user, request.data.get("quantity")))

    @action(detail=False, methods=["get"])
    def plan(self, request):
        mr = get_object_or_404(MaterialRequirement.objects.select_related("order"), pk=request.query_params.get("requirement"))
        return Response({"requirement": mr.id, "mr_no": mr.mr_no, "order": mr.order_id,
                         "oc_no": mr.order.oc_no if mr.order else None, "lines": services.allocation_plan(mr)})

    @action(detail=False, methods=["post"])
    def auto(self, request):
        mr = get_object_or_404(MaterialRequirement.objects.select_related("order"), pk=request.data.get("requirement"))
        wh_id = request.data.get("warehouse")
        warehouse = get_object_or_404(Warehouse, pk=wh_id) if wh_id else None
        made = services.auto_allocate(mr, request.user, warehouse)
        if not made:
            raise ValidationError({"detail": "Nothing to allocate: either everything is covered or there is no free stock."})
        return Response(self.get_serializer(made, many=True).data, status=status.HTTP_201_CREATED)
