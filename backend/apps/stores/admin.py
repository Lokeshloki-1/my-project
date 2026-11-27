from django.contrib import admin

from .models import ActivityLog, GoodsReceipt, GoodsReceiptLine, Material, MaterialAllocation, MaterialMovement, MaterialStock


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ["code", "category", "description", "colour", "unit", "reorder_level"]
    list_filter = ["category", "company"]
    search_fields = ["code", "description", "colour"]


@admin.register(MaterialStock)
class MaterialStockAdmin(admin.ModelAdmin):
    # Read-only: stock changes only through receipts, issues and adjustments.
    list_display = ["material", "warehouse", "on_hand", "allocated", "value"]
    list_filter = ["warehouse"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MaterialMovement)
class MaterialMovementAdmin(admin.ModelAdmin):
    list_display = ["created_at", "material", "warehouse", "movement_type", "quantity", "balance_after", "reference"]
    list_filter = ["movement_type", "warehouse"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class GRNLineInline(admin.TabularInline):
    model = GoodsReceiptLine
    extra = 0
    readonly_fields = ["material", "accepted_qty", "rejected_qty", "result", "remarks"]


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ["grn_no", "purchase_order", "supplier", "warehouse", "received_on", "status"]
    list_filter = ["status", "warehouse", "company"]
    search_fields = ["grn_no", "challan_no", "invoice_no"]
    readonly_fields = ["status", "supplier"]
    inlines = [GRNLineInline]


@admin.register(MaterialAllocation)
class MaterialAllocationAdmin(admin.ModelAdmin):
    list_display = ["order", "material", "warehouse", "quantity", "issued_qty", "released_qty", "status"]
    list_filter = ["status", "warehouse"]
    readonly_fields = ["quantity", "issued_qty", "released_qty", "status"]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["doc_type", "doc_id", "action", "user", "created_at"]
