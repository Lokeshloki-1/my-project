from rest_framework import viewsets

from apps.accounts.permissions import IsManagerOrReadOnly

from .models import Company
from .serializers import CompanySerializer


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["is_active", "country"]
    search_fields = ["name", "code", "city"]
    ordering_fields = ["name", "created_at"]
