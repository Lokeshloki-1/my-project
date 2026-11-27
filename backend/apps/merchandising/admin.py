from django.contrib import admin

from .models import ActivityLog, CostSheet, CostSheetLine, OrderConfirmation, OrderConfirmationLine, Quotation, QuotationLine


class CostSheetLineInline(admin.TabularInline):
    model = CostSheetLine
    extra = 0
    readonly_fields = ["amount"]


@admin.register(CostSheet)
class CostSheetAdmin(admin.ModelAdmin):
    # Status changes must go through the API so they are checked and logged.
    list_display = ["cost_no", "style_no", "buyer", "currency", "fob_price", "status"]
    list_filter = ["status", "category", "company"]
    search_fields = ["cost_no", "style_no", "style_name"]
    readonly_fields = ["status", "direct_cost", "overhead_amount", "total_cost", "margin_amount", "commission_amount", "fob_price"]
    inlines = [CostSheetLineInline]


class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 0
    readonly_fields = ["amount"]


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ["quote_no", "buyer", "quote_date", "valid_until", "currency", "total_amount", "status"]
    list_filter = ["status", "company"]
    search_fields = ["quote_no", "buyer__legal_name"]
    readonly_fields = ["status", "total_quantity", "total_amount"]
    inlines = [QuotationLineInline]


class OrderLineInline(admin.TabularInline):
    model = OrderConfirmationLine
    extra = 0
    readonly_fields = ["amount"]


@admin.register(OrderConfirmation)
class OrderConfirmationAdmin(admin.ModelAdmin):
    list_display = ["oc_no", "buyer", "buyer_po_no", "ship_date", "currency", "total_amount", "status"]
    list_filter = ["status", "company"]
    search_fields = ["oc_no", "buyer_po_no", "buyer__legal_name"]
    readonly_fields = ["status", "credit_override", "override_reason", "total_quantity", "total_amount"]
    inlines = [OrderLineInline]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["doc_type", "doc_id", "action", "user", "created_at"]
    list_filter = ["doc_type", "action"]
