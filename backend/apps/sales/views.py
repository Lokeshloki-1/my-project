from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from apps.accounts.permissions import IsManagerOrReadOnly

from .models import Customer, Product, SalesOrder
from .serializers import CustomerSerializer, ProductSerializer, SalesOrderSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    filterset_fields = ["company", "country"]
    search_fields = ["name", "email", "phone", "city"]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company", "is_active"]
    search_fields = ["sku", "name", "hs_code"]


class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.select_related("company", "customer", "salesperson").prefetch_related(
        "items__product"
    )
    serializer_class = SalesOrderSerializer
    filterset_fields = {
        "company": ["exact"],
        "customer": ["exact"],
        "salesperson": ["exact"],
        "status": ["exact"],
        "order_date": ["gte", "lte"],
    }
    search_fields = ["order_no", "customer__name", "notes"]
    ordering_fields = ["order_date", "total", "created_at"]

    def perform_destroy(self, instance):
        # Keep an audit trail: only drafts can be deleted, others must be cancelled.
        if instance.status != SalesOrder.Status.DRAFT:
            raise ValidationError("Only draft orders can be deleted. Cancel the order instead.")
        instance.delete()
