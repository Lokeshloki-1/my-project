from django.db import transaction
from django.http import HttpResponse
import json
import logging

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsFinanceOrReadOnly
from apps.inventory.services import return_for_order
from apps.sales.models import SalesOrder

from . import razorpay, upi
from .models import Invoice, Payment, UpiQrCode
from .pdf import render_invoice_pdf
from .serializers import InvoiceDetailSerializer, InvoiceSerializer, PaymentSerializer, UpiQrCodeSerializer

log = logging.getLogger(__name__)


class InvoiceViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Invoices can be created, viewed and have their due date / notes edited — never deleted."""

    queryset = Invoice.objects.select_related("company", "customer", "sales_order")
    permission_classes = [IsFinanceOrReadOnly]
    filterset_fields = {
        "company": ["exact"], "customer": ["exact"], "status": ["exact", "in"],
        "invoice_date": ["gte", "lte"], "due_date": ["lt", "gte"],
    }
    search_fields = ["invoice_no", "customer__name", "sales_order__order_no"]
    ordering_fields = ["invoice_date", "due_date", "total"]

    def get_serializer_class(self):
        return InvoiceDetailSerializer if self.action == "retrieve" else InvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("retrieve", "pdf"):
            qs = qs.prefetch_related("sales_order__items__product", "payments")
        return qs

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        response = HttpResponse(render_invoice_pdf(invoice), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_no}.pdf"'
        return response

    @action(detail=True, methods=["get", "post"], url_path="upi-qr", permission_classes=[IsAuthenticated])
    def upi_qr(self, request, pk=None):
        """
        POST: make a new Razorpay UPI QR for the invoice balance (any logged-in user, e.g. counter staff —
              the payment itself is only recorded once Razorpay confirms it).
        GET:  the latest QR for this invoice; while it is active, checks Razorpay for a payment.
        """
        invoice = self.get_object()
        if request.method == "POST":
            qr = upi.create_qr_for_invoice(invoice, user=request.user)
            return Response(UpiQrCodeSerializer(qr).data, status=status.HTTP_201_CREATED)
        qr = invoice.upi_qr_codes.first()
        if not qr:
            return Response({"detail": "No QR code yet."}, status=status.HTTP_404_NOT_FOUND)
        qr = upi.sync_qr(qr)
        return Response(UpiQrCodeSerializer(UpiQrCode.objects.select_related("invoice").get(pk=qr.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel an invoice that has no payments. Its sales order is cancelled and its stock returned."""
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=self.get_object().pk)
            if invoice.status == Invoice.Status.CANCELLED:
                raise ValidationError("Invoice is already cancelled.")
            if invoice.payments.exists():
                raise ValidationError("Invoices with payments cannot be cancelled. Delete the payments first.")
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status", "updated_at"])
            order = SalesOrder.objects.select_for_update().get(pk=invoice.sales_order_id)
            order.status = SalesOrder.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])
            return_for_order(order, user=request.user)  # goods come back into stock
        return Response(InvoiceSerializer(invoice).data)


class PaymentViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Payments cannot be edited. To fix a mistake, delete the payment (admin/manager) and record it again."""

    queryset = Payment.objects.select_related("invoice__customer")
    serializer_class = PaymentSerializer
    permission_classes = [IsFinanceOrReadOnly]
    filterset_fields = {
        "invoice": ["exact"], "method": ["exact"], "invoice__company": ["exact"],
        "payment_date": ["gte", "lte"],
    }
    search_fields = ["reference", "invoice__invoice_no", "invoice__customer__name"]
    ordering_fields = ["payment_date", "amount"]

    def perform_destroy(self, instance):
        if not self.request.user.is_manager_or_admin:
            raise ValidationError("Only admins and managers can delete payments.")
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=instance.invoice_id)
            if invoice.status == Invoice.Status.CANCELLED:
                raise ValidationError("The invoice is cancelled.")
            instance.delete()
            invoice.refresh_payment_status()


class RazorpayWebhookView(APIView):
    """
    Razorpay calls this URL when a QR code is paid (event qr_code.credited).
    No login: instead every request must carry a valid X-Razorpay-Signature.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.body  # the signature is over the exact raw bytes
        if not razorpay.verify_webhook_signature(raw, request.headers.get("X-Razorpay-Signature", "")):
            log.warning("Rejected Razorpay webhook with a bad or missing signature")
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            event = json.loads(raw)
        except ValueError:
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)
        result = upi.handle_webhook(event)
        return Response({"status": result})
