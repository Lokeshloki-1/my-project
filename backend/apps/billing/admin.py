from django.contrib import admin

from .models import Invoice, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # record payments through the app so balances stay correct

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_no", "invoice_date", "due_date", "customer", "total", "amount_paid", "status")
    list_filter = ("company", "status")
    search_fields = ("invoice_no", "customer__name")
    readonly_fields = [f.name for f in Invoice._meta.fields]
    inlines = [PaymentInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_date", "invoice", "amount", "method", "reference")
    list_filter = ("method",)
    search_fields = ("reference", "invoice__invoice_no")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
