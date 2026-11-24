from django.contrib import admin

from .models import Shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("shipment_no", "company", "customer", "destination_country", "mode", "status", "landed_cost")
    list_filter = ("company", "status", "mode", "destination_country")
    search_fields = ("shipment_no", "tracking_no", "customer__name")
    readonly_fields = ("shipment_no", "incoterm", "customs_duty", "import_vat", "landed_cost")
