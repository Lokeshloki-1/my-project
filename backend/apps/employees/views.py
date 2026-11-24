from rest_framework import viewsets

from apps.accounts.permissions import IsManagerOrReadOnly

from .models import Department, Employee
from .serializers import DepartmentSerializer, EmployeeSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("company")
    serializer_class = DepartmentSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company"]
    search_fields = ["name"]


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related("company", "department")
    serializer_class = EmployeeSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company", "department", "status"]
    search_fields = ["employee_code", "first_name", "last_name", "email", "designation"]
    ordering_fields = ["first_name", "date_joined", "monthly_sales_target"]
