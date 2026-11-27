from django.contrib import admin

from .models import Buyer, BuyerContact, BuyerEnquiry, BuyerRequirement, BuyerStatusLog, CreditCheck


@admin.register(BuyerEnquiry)
class BuyerEnquiryAdmin(admin.ModelAdmin):
    list_display = ["enquiry_no", "buyer_name", "country", "source", "status", "received_on"]
    list_filter = ["status", "source", "company"]
    search_fields = ["enquiry_no", "buyer_name", "contact_name", "email"]


class BuyerContactInline(admin.TabularInline):
    model = BuyerContact
    extra = 0


class BuyerRequirementInline(admin.StackedInline):
    model = BuyerRequirement
    extra = 0


class CreditCheckInline(admin.TabularInline):
    model = CreditCheck
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in CreditCheck._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


class BuyerStatusLogInline(admin.TabularInline):
    model = BuyerStatusLog
    extra = 0
    can_delete = False
    readonly_fields = ["from_status", "to_status", "note", "user", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Buyer)
class BuyerAdmin(admin.ModelAdmin):
    # Status changes must go through the API so they are checked and logged.
    list_display = ["buyer_code", "legal_name", "country", "buyer_type", "status", "created_at"]
    list_filter = ["status", "buyer_type", "company"]
    search_fields = ["buyer_code", "legal_name", "trade_name"]
    readonly_fields = ["buyer_code", "status", "approved_by", "approved_at", "rejection_reason", "customer", "created_by"]
    inlines = [BuyerContactInline, BuyerRequirementInline, CreditCheckInline, BuyerStatusLogInline]
