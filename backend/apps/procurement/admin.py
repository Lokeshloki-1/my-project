from django.contrib import admin

from .models import (
    ActivityLog, MaterialRequirement, PurchaseOrder, PurchaseOrderLine, RequirementLine, RFQ, RFQLine, Supplier,
    SupplierQuote, SupplierQuoteLine,
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "country", "lead_time_days", "is_active"]
    list_filter = ["is_active", "country", "company"]
    search_fields = ["name", "contact_name", "email", "tax_id"]


class RequirementLineInline(admin.TabularInline):
    model = RequirementLine
    extra = 0


@admin.register(MaterialRequirement)
class MaterialRequirementAdmin(admin.ModelAdmin):
    # Status changes must go through the API so they are checked and logged.
    list_display = ["mr_no", "title", "needed_by", "status"]
    list_filter = ["status", "company"]
    readonly_fields = ["status", "warnings"]
    inlines = [RequirementLineInline]


class RFQLineInline(admin.TabularInline):
    model = RFQLine
    extra = 0


@admin.register(RFQ)
class RFQAdmin(admin.ModelAdmin):
    list_display = ["rfq_no", "title", "reply_by", "status", "awarded_supplier"]
    list_filter = ["status", "company"]
    readonly_fields = ["status", "awarded_supplier"]
    inlines = [RFQLineInline]


class QuoteLineInline(admin.TabularInline):
    model = SupplierQuoteLine
    extra = 0


@admin.register(SupplierQuote)
class SupplierQuoteAdmin(admin.ModelAdmin):
    list_display = ["rfq", "supplier", "currency", "total", "complete"]
    inlines = [QuoteLineInline]


class POLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    readonly_fields = ["amount"]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["po_no", "supplier", "order_date", "delivery_date", "currency", "total", "status"]
    list_filter = ["status", "company"]
    search_fields = ["po_no", "supplier__name"]
    readonly_fields = ["status", "total"]
    inlines = [POLineInline]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["doc_type", "doc_id", "action", "user", "created_at"]
    list_filter = ["doc_type", "action"]
