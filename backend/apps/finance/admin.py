from django.contrib import admin

from .models import ExportInvoice, ExportReceipt, OrderExpense


class ReceiptInline(admin.TabularInline):
    model = ExportReceipt
    extra = 0
    readonly_fields = ["amount_inr", "exchange_gain_loss_inr"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ExportInvoice)
class ExportInvoiceAdmin(admin.ModelAdmin):
    # Receipts are recorded through the API so balances and gain/loss stay correct.
    list_display = ["invoice_no", "buyer", "invoice_date", "currency", "amount", "amount_received", "due_date", "status"]
    list_filter = ["status", "currency", "company"]
    search_fields = ["invoice_no", "buyer__legal_name"]
    readonly_fields = ["amount", "amount_inr", "amount_received", "bank_charges", "status"]
    inlines = [ReceiptInline]


@admin.register(OrderExpense)
class OrderExpenseAdmin(admin.ModelAdmin):
    list_display = ["order", "date", "category", "amount_inr", "note"]
    list_filter = ["category"]
