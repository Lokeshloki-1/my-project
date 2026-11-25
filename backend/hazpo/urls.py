from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.billing.views import InvoiceViewSet, PaymentViewSet, RazorpayWebhookView
from apps.companies.views import CompanyViewSet
from apps.ddp.views import ShipmentViewSet
from apps.employees.views import DepartmentViewSet, EmployeeViewSet
from apps.inventory.views import StockLevelViewSet, StockMovementViewSet, WarehouseViewSet
from apps.sales.views import CustomerViewSet, ProductViewSet, SalesOrderViewSet

router = DefaultRouter()
router.register("companies", CompanyViewSet)
router.register("departments", DepartmentViewSet)
router.register("employees", EmployeeViewSet)
router.register("customers", CustomerViewSet)
router.register("products", ProductViewSet)
router.register("sales-orders", SalesOrderViewSet)
router.register("ddp/shipments", ShipmentViewSet)
router.register("invoices", InvoiceViewSet)
router.register("payments", PaymentViewSet)
router.register("warehouses", WarehouseViewSet)
router.register("stock-levels", StockLevelViewSet)
router.register("stock-movements", StockMovementViewSet)

def health(request):
    """For uptime monitors and Docker: 200 when the app and database are working."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - any DB failure means unhealthy
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/razorpay/webhook/", RazorpayWebhookView.as_view(), name="razorpay-webhook"),
    path("api/", include(router.urls)),
]
