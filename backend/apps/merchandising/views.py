from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.buyers.services import Conflict

from . import services
from .models import CostSheet, OrderConfirmation, Quotation
from .serializers import (
    CostSheetListSerializer,
    CostSheetSerializer,
    OrderConfirmationListSerializer,
    OrderConfirmationSerializer,
    QuotationListSerializer,
    QuotationSerializer,
)


def _reason(request, key="reason"):
    return str(request.data.get(key, "")).strip()


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


class CostSheetViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                       mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = CostSheet.objects.select_related("buyer", "approved_by").prefetch_related("lines")
    list_serializer = CostSheetListSerializer
    detail_serializer = CostSheetSerializer
    filterset_fields = ["company", "buyer", "status", "category", "currency"]
    search_fields = ["cost_no", "style_no", "style_name", "buyer__legal_name"]
    ordering_fields = ["created_at", "fob_price", "style_no"]

    def perform_destroy(self, instance):
        services.ensure_draft(instance, "cost sheet")
        if instance.quotation_lines.exists() or instance.order_lines.exists():
            raise Conflict("This cost sheet is used on a quotation and cannot be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._detail(services.approve_cost_sheet(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._detail(services.reopen_cost_sheet(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def copy(self, request, pk=None):
        return self._detail(services.copy_cost_sheet(self.get_object(), request.user), status.HTTP_201_CREATED)


class QuotationViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                       mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = Quotation.objects.select_related("buyer", "order_confirmation").prefetch_related("lines__cost_sheet")
    list_serializer = QuotationListSerializer
    detail_serializer = QuotationSerializer
    filterset_fields = {"company": ["exact"], "buyer": ["exact"], "status": ["exact"], "quote_date": ["gte", "lte"]}
    search_fields = ["quote_no", "buyer__legal_name", "lines__style_no"]
    ordering_fields = ["quote_date", "total_amount", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct() if self.request.query_params.get("search") else qs

    def perform_destroy(self, instance):
        if instance.status != Quotation.Status.DRAFT:
            raise Conflict("Only draft quotations can be deleted. Cancel it instead.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        return self._detail(services.send_quotation(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._detail(services.reopen_quotation(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._detail(services.accept_quotation(self.get_object(), request.user, _reason(request, "note")))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._detail(services.reject_quotation(self.get_object(), request.user, _reason(request)))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_quotation(self.get_object(), request.user, _reason(request)))

    @action(detail=True, methods=["post"], url_path="create-order")
    def create_order(self, request, pk=None):
        order, created = services.create_order(self.get_object(), request.user)
        fresh = OrderConfirmationViewSet.queryset.get(pk=order.pk)
        data = OrderConfirmationSerializer(fresh, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class OrderConfirmationViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    """Orders are created from accepted quotations (POST /quotations/{id}/create-order/) and never deleted."""

    queryset = OrderConfirmation.objects.select_related("buyer", "quotation", "confirmed_by").prefetch_related(
        "lines__cost_sheet"
    )
    list_serializer = OrderConfirmationListSerializer
    detail_serializer = OrderConfirmationSerializer
    filterset_fields = {"company": ["exact"], "buyer": ["exact"], "status": ["exact"], "ship_date": ["gte", "lte"]}
    search_fields = ["oc_no", "buyer_po_no", "buyer__legal_name", "lines__style_no"]
    ordering_fields = ["created_at", "ship_date", "total_amount"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct() if self.request.query_params.get("search") else qs

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST", detail="Create an order from an accepted quotation: POST /api/quotations/{id}/create-order/.")

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = services.confirm_order(self.get_object(), request.user, _reason(request, "override_reason"))
        return self._detail(order)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_order(self.get_object(), request.user, _reason(request)))
