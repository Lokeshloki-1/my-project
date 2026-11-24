from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Shipment
from .serializers import LandedCostQuoteSerializer, ShipmentSerializer


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.select_related("company", "customer", "sales_order")
    serializer_class = ShipmentSerializer
    filterset_fields = ["company", "customer", "status", "mode", "destination_country"]
    search_fields = ["shipment_no", "tracking_no", "customer__name", "carrier"]
    ordering_fields = ["created_at", "ship_date", "landed_cost"]

    def perform_destroy(self, instance):
        if instance.status != Shipment.Status.BOOKED:
            raise ValidationError("Only booked shipments can be deleted. Cancel it instead.")
        instance.delete()

    @action(detail=False, methods=["post"])
    def quote(self, request):
        """Calculate DDP landed cost without saving — used by the calculator in the UI."""
        data = LandedCostQuoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        s = Shipment(**data.validated_data)
        s.calculate_costs()
        return Response({
            "cif_value": s.cif_value,
            "customs_duty": s.customs_duty,
            "import_vat": s.import_vat,
            "landed_cost": s.landed_cost,
        })
