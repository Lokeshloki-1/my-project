from django.contrib import admin

from .models import ActivityLog, ProductionEntry, ProductionLine, ProductionOrder


@admin.register(ProductionLine)
class ProductionLineAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "operators", "working_minutes", "efficiency_pct", "is_active"]
    list_filter = ["is_active", "company"]


class EntryInline(admin.TabularInline):
    model = ProductionEntry
    extra = 0
    readonly_fields = ["stage", "date", "sizes", "quantity", "rejected", "line", "entered_by"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    # Output is recorded through the API so stage limits are checked.
    list_display = ["wo_no", "style_no", "order", "line", "quantity", "planned_start", "planned_end", "status"]
    list_filter = ["status", "line", "company"]
    search_fields = ["wo_no", "style_no"]
    readonly_fields = ["status", "style_no"]
    inlines = [EntryInline]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["production_order", "action", "user", "created_at"]
