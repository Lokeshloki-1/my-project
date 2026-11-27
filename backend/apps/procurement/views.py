from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.buyers.services import Conflict
from apps.merchandising.models import OrderConfirmation

from . import services
from .models import MaterialRequirement, PurchaseOrder, PurchaseOrderLine, RequirementLine, RFQ, RFQLine, Supplier
from .serializers import (
    MaterialRequirementListSerializer,
    MaterialRequirementSerializer,
    PurchaseOrderListSerializer,
    PurchaseOrderSerializer,
    QuoteInputSerializer,
    RFQListSerializer,
    RFQSerializer,
    SupplierSerializer,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filterset_fields = ["company", "country", "is_active"]
    search_fields = ["name", "contact_name", "email", "city", "tax_id"]

    def perform_destroy(self, instance):
        if instance.purchase_orders.exists() or instance.rfqs.exists():
            raise Conflict("This supplier has RFQs or POs. Mark it inactive instead.")
        instance.delete()


class _DocViewSet(viewsets.GenericViewSet):
    list_serializer = None
    detail_serializer = None

    def get_serializer_class(self):
        return self.list_serializer if self.action == "list" else self.detail_serializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=obj.pk)
        return Response(self.detail_serializer(fresh, context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._detail(serializer.save(), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return self._detail(serializer.save())


_LINE_PREFETCH = Prefetch(
    "lines", queryset=RequirementLine.objects.prefetch_related("po_lines__order", "rfq_lines__rfq")
)


class MaterialRequirementViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                                 mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = MaterialRequirement.objects.select_related("order", "buyer", "approved_by").prefetch_related(_LINE_PREFETCH)
    list_serializer = MaterialRequirementListSerializer
    detail_serializer = MaterialRequirementSerializer
    filterset_fields = ["company", "status", "buyer", "order"]
    search_fields = ["mr_no", "title", "order__oc_no", "order__buyer_po_no", "lines__description"]
    ordering_fields = ["created_at", "needed_by"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct() if self.request.query_params.get("search") else qs

    def perform_destroy(self, instance):
        services.ensure_draft(instance, "requirement")
        if instance.rfqs.exists() or instance.purchase_orders.exists():
            raise Conflict("This requirement has RFQs or POs and cannot be deleted.")
        instance.delete()

    @action(detail=False, methods=["post"])
    def generate(self, request):
        order = get_object_or_404(OrderConfirmation, pk=request.data.get("order"))
        try:
            wastage = Decimal(str(request.data.get("wastage_pct", "5")))
        except InvalidOperation:
            raise ValidationError({"wastage_pct": "Give a number."}) from None
        if not (0 <= wastage <= 100):
            raise ValidationError({"wastage_pct": "Wastage must be between 0 and 100."})
        mr, created = services.generate_requirement(order, request.user, wastage)
        return self._detail(mr, status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def recalculate(self, request, pk=None):
        return self._detail(services.recalculate_requirement(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._detail(services.approve_requirement(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._detail(services.reopen_requirement(self.get_object(), request.user))


class RFQViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                 mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = RFQ.objects.select_related("requirement", "awarded_supplier").prefetch_related(
        "suppliers", Prefetch("lines", queryset=RFQLine.objects.select_related("requirement_line__requirement")),
        "purchase_orders",
    )
    list_serializer = RFQListSerializer
    detail_serializer = RFQSerializer
    filterset_fields = ["company", "status", "requirement"]
    search_fields = ["rfq_no", "title", "suppliers__name", "lines__description"]
    ordering_fields = ["created_at", "reply_by"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct() if self.request.query_params.get("search") else qs

    def perform_destroy(self, instance):
        services.ensure_draft(instance, "RFQ")
        instance.delete()

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        return self._detail(services.send_rfq(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def quotes(self, request, pk=None):
        rfq = self.get_object()
        data = QuoteInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = dict(data.validated_data)
        supplier, lines = d.pop("supplier"), d.pop("lines")
        d["currency"] = d["currency"].upper()
        services.record_quote(rfq, request.user, supplier, d, lines)
        return self._detail(rfq)

    @action(detail=True, methods=["post"])
    def award(self, request, pk=None):
        supplier = get_object_or_404(Supplier, pk=request.data.get("supplier"))
        po = services.award_rfq(self.get_object(), request.user, supplier)
        fresh = PurchaseOrderViewSet.queryset.get(pk=po.pk)
        return Response(PurchaseOrderSerializer(fresh, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_rfq(self.get_object(), request.user, str(request.data.get("reason", "")).strip()))


class PurchaseOrderViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                           mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = PurchaseOrder.objects.select_related("supplier", "requirement", "rfq", "approved_by").prefetch_related(
        Prefetch("lines", queryset=PurchaseOrderLine.objects.select_related("requirement_line__requirement").prefetch_related(
            "requirement_line__po_lines__order"))
    )
    list_serializer = PurchaseOrderListSerializer
    detail_serializer = PurchaseOrderSerializer
    filterset_fields = {"company": ["exact"], "supplier": ["exact"], "status": ["exact"], "requirement": ["exact"],
                        "order_date": ["gte", "lte"]}
    search_fields = ["po_no", "supplier__name", "lines__description"]
    ordering_fields = ["order_date", "delivery_date", "total", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct() if self.request.query_params.get("search") else qs

    def perform_destroy(self, instance):
        services.ensure_draft(instance, "purchase order")
        if instance.rfq_id:
            raise Conflict("This PO came from an RFQ award. Cancel it instead.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._detail(services.approve_po(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        return self._detail(services.send_po(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_po(self.get_object(), request.user, str(request.data.get("reason", "")).strip()))
