from django.contrib import admin

from .models import StockLevel, StockMovement, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company", "city", "is_active")
    list_filter = ("company", "is_active")


class ReadOnlyAdmin(admin.ModelAdmin):
    """Stock is changed only through the app, so balances and the ledger always agree."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockLevel)
class StockLevelAdmin(ReadOnlyAdmin):
    list_display = ("product", "warehouse", "quantity", "updated_at")
    list_filter = ("warehouse",)
    search_fields = ("product__sku", "product__name")


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "movement_type", "product", "warehouse", "quantity", "balance_after", "reference")
    list_filter = ("movement_type", "warehouse")
    search_fields = ("product__sku", "reference")
