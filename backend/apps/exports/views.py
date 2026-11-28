from datetime import date

from django.db.models import Prefetch
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.buyers.services import Conflict
from apps.merchandising.models import OrderConfirmation

from . import pdf, services
from .models import CartonGroup, ExportDocument, ExportShipment, PackingList
from .serializers import (
    ExportDocumentSerializer,
    ExportShipmentListSerializer,
    ExportShipmentSerializer,
    PackingListListSerializer,
    PackingListSerializer,
)


def _date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({"date": "Use YYYY-MM-DD."}) from None


def _pdf(content, filename):
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class _DocViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                  viewsets.GenericViewSet):
    list_serializer = detail_serializer = None

    def get_serializer_class(self):
        return self.list_serializer if self.action == "list" else self.detail_serializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        return Response(self.detail_serializer(self.get_queryset().get(pk=obj.pk), context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._detail(s.save(), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        s = self.get_serializer(self.get_object(), data=request.data, partial=kwargs.pop("partial", False))
        s.is_valid(raise_exception=True)
        return self._detail(s.save())


class PackingListViewSet(_DocViewSet, mixins.DestroyModelMixin):
    queryset = PackingList.objects.select_related("order__buyer", "shipment", "finalized_by").prefetch_related(
        Prefetch("groups", queryset=CartonGroup.objects.select_related("production_order")))
    list_serializer, detail_serializer = PackingListListSerializer, PackingListSerializer
    filterset_fields = ["company", "order", "status", "shipment"]
    search_fields = ["pl_no", "order__oc_no", "order__buyer_po_no", "groups__style_no"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct() if self.request.query_params.get("search") else qs

    def perform_destroy(self, instance):
        if instance.status != PackingList.Status.DRAFT:
            raise Conflict("Only draft packing lists can be deleted.")
        instance.delete()

    @action(detail=False, methods=["get"], url_path="pack-status")
    def pack_status(self, request):
        """Per work order of an order: finished, passed final inspection, packed, still packable."""
        order = get_object_or_404(OrderConfirmation, pk=request.query_params.get("order"))
        return Response([services.wo_pack_status(wo) for wo in order.production_orders.exclude(status="cancelled").prefetch_related("entries")])

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        return self._detail(services.finalize_packing_list(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._detail(services.reopen_packing_list(self.get_object(), request.user))

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        pl = self.get_object()
        return _pdf(pdf.render_packing_list(pl, pl.shipment), f"{pl.pl_no}.pdf")


class ExportShipmentViewSet(_DocViewSet):
    queryset = ExportShipment.objects.select_related("order__buyer", "company").prefetch_related(
        "order__lines", "documents",
        Prefetch("packing_lists", queryset=PackingList.objects.select_related("order__buyer", "shipment").prefetch_related("groups")))
    list_serializer, detail_serializer = ExportShipmentListSerializer, ExportShipmentSerializer
    filterset_fields = {"company": ["exact"], "order": ["exact"], "status": ["exact", "in"], "mode": ["exact"], "etd": ["gte", "lte"]}
    search_fields = ["shipment_no", "invoice_no", "order__oc_no", "order__buyer__legal_name", "bl_no", "container_no", "vessel"]

    @action(detail=True, methods=["post"])
    def book(self, request, pk=None):
        return self._detail(services.book_shipment(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        return self._detail(services.ship(self.get_object(), request.user, _date(request.data.get("on_board_date"))))

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        return self._detail(services.deliver(self.get_object(), request.user, _date(request.data.get("delivered_date"))))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_shipment(self.get_object(), request.user, str(request.data.get("reason", "")).strip()))

    @action(detail=True, methods=["get"], url_path="commercial-invoice")
    def commercial_invoice(self, request, pk=None):
        s = self.get_object()
        if not s.packing_lists.exists():
            raise Conflict("Add packing lists first.")
        return _pdf(pdf.render_commercial_invoice(s), f"{s.invoice_no}.pdf")


class ExportDocumentViewSet(mixins.UpdateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ExportDocument.objects.select_related("shipment")
    serializer_class = ExportDocumentSerializer
