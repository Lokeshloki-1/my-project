from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.accounts.permissions import IsFinanceOrReadOnly
from apps.exports import pdf as export_pdf
from apps.exports.models import ExportShipment
from apps.merchandising.models import OrderConfirmation

from . import services
from .models import ExportInvoice, ExportReceipt, OrderExpense
from .serializers import ExportInvoiceListSerializer, ExportInvoiceSerializer, ExportReceiptSerializer, OrderExpenseSerializer


def _date(value, default=None):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({"date": "Use YYYY-MM-DD."}) from None


class ExportInvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Raised from shipped shipments (POST create-from-shipment); only notes and due date can be edited."""

    queryset = ExportInvoice.objects.select_related("buyer", "order", "shipment__order").prefetch_related(
        "receipts__created_by", "shipment__packing_lists__groups", "shipment__order__lines")
    permission_classes = [IsFinanceOrReadOnly]
    filterset_fields = {"company": ["exact"], "buyer": ["exact"], "order": ["exact"], "status": ["exact", "in"],
                        "invoice_date": ["gte", "lte"], "due_date": ["lt", "gte"]}
    search_fields = ["invoice_no", "buyer__legal_name", "order__oc_no", "order__buyer_po_no", "shipment__shipment_no"]
    ordering_fields = ["invoice_date", "due_date", "amount"]

    def get_serializer_class(self):
        return ExportInvoiceListSerializer if self.action == "list" else ExportInvoiceSerializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        return Response(ExportInvoiceSerializer(self.get_queryset().get(pk=obj.pk), context={"request": self.request}).data, status=code)

    def update(self, request, *args, **kwargs):
        allowed = {k: v for k, v in request.data.items() if k in ("notes", "due_date")}
        s = ExportInvoiceSerializer(self.get_object(), data=allowed, partial=True, context={"request": request})
        s.is_valid(raise_exception=True)
        return self._detail(s.save())

    @action(detail=False, methods=["post"], url_path="create-from-shipment")
    def create_from_shipment(self, request):
        shipment = get_object_or_404(ExportShipment, pk=request.data.get("shipment"))
        inv, created = services.create_invoice(shipment, request.user, request.data.get("exchange_rate"), _date(request.data.get("invoice_date")))
        return self._detail(inv, status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._detail(services.cancel_invoice(self.get_object(), request.user, str(request.data.get("reason", "")).strip()))

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        inv = self.get_object()
        response = HttpResponse(export_pdf.render_commercial_invoice(inv.shipment), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{inv.invoice_no}.pdf"'
        return response

    @action(detail=False, methods=["get"])
    def ageing(self, request):
        return Response(services.ageing(_date(request.query_params.get("as_of"), timezone.localdate()), request.query_params.get("company") or None))

    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(services.summary(request.query_params.get("company") or None))


class ExportReceiptViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = ExportReceipt.objects.select_related("invoice", "created_by")
    serializer_class = ExportReceiptSerializer
    permission_classes = [IsFinanceOrReadOnly]
    filterset_fields = {"invoice": ["exact"], "received_on": ["gte", "lte"], "method": ["exact"]}

    def destroy(self, request, *args, **kwargs):
        services.delete_receipt(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderExpenseViewSet(viewsets.ModelViewSet):
    queryset = OrderExpense.objects.select_related("order")
    serializer_class = OrderExpenseSerializer
    permission_classes = [IsFinanceOrReadOnly]
    filterset_fields = ["company", "order", "category"]


class OrderProfitViewSet(viewsets.ViewSet):
    """Profit per confirmed order: invoiced revenue minus materials issued, conversion, expenses and bank charges."""

    def list(self, request):
        rows = []
        for order in services.orders_with_money(request.query_params.get("company") or None):
            p = services.order_profit(order)
            p.pop("styles")
            rows.append(p)
        return Response(sorted(rows, key=lambda r: -(r["invoiced_inr"] or 0)))

    def retrieve(self, request, pk=None):
        order = get_object_or_404(OrderConfirmation.objects.select_related("buyer"), pk=pk)
        data = services.order_profit(order)
        data["expenses"] = OrderExpenseSerializer(order.expenses.all(), many=True).data
        data["invoices"] = ExportInvoiceListSerializer(order.export_invoices.all(), many=True, context={"request": request}).data
        return Response(data)
