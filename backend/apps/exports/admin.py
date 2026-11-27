from django.contrib import admin

from .models import CartonGroup, ExportDocument, ExportShipment, PackingList


class CartonGroupInline(admin.TabularInline):
    model = CartonGroup
    extra = 0


@admin.register(PackingList)
class PackingListAdmin(admin.ModelAdmin):
    list_display = ["pl_no", "order", "pack_date", "total_cartons", "total_pcs", "cbm", "status"]
    list_filter = ["status", "company"]
    readonly_fields = ["status", "total_cartons", "total_pcs", "net_weight", "gross_weight", "cbm"]
    inlines = [CartonGroupInline]


class DocumentInline(admin.TabularInline):
    model = ExportDocument
    extra = 0


@admin.register(ExportShipment)
class ExportShipmentAdmin(admin.ModelAdmin):
    list_display = ["shipment_no", "order", "mode", "port_of_discharge", "etd", "bl_no", "status"]
    list_filter = ["status", "mode", "company"]
    search_fields = ["shipment_no", "invoice_no", "bl_no", "container_no"]
    readonly_fields = ["status", "invoice_no", "on_board_date", "delivered_date"]
    inlines = [DocumentInline]
