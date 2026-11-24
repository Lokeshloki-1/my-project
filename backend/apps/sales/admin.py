from django.contrib import admin

from .models import Customer, Product, SalesOrder, SalesOrderItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "city", "country", "phone")
    list_filter = ("company", "country")
    search_fields = ("name", "email", "phone")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "company", "unit_price", "tax_rate", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("sku", "name")


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ("order_no", "order_date", "company", "customer", "salesperson", "status", "total")
    list_filter = ("company", "status", "order_date")
    search_fields = ("order_no", "customer__name")
    readonly_fields = ("order_no", "subtotal", "tax_amount", "total")
    inlines = [SalesOrderItemInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalculate_totals()
