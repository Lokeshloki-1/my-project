from django.contrib import admin

from .models import ActivityLog, BOMItem, Measurement, Sample, SampleMeasurement, TechPack


class MeasurementInline(admin.TabularInline):
    model = Measurement
    extra = 0


class BOMInline(admin.TabularInline):
    model = BOMItem
    extra = 0


@admin.register(TechPack)
class TechPackAdmin(admin.ModelAdmin):
    # Status changes must go through the API so they are checked and logged.
    list_display = ["tp_no", "revision", "style_no", "buyer", "season", "status", "production_approved"]
    list_filter = ["status", "production_approved", "category", "company"]
    search_fields = ["tp_no", "style_no", "style_name"]
    readonly_fields = ["status", "revision", "production_approved"]
    inlines = [MeasurementInline, BOMInline]


class SampleMeasurementInline(admin.TabularInline):
    model = SampleMeasurement
    extra = 0
    readonly_fields = ["spec", "tolerance"]


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ["sample_no", "tech_pack", "sample_type", "round", "status", "due_date"]
    list_filter = ["status", "sample_type", "company"]
    search_fields = ["sample_no", "tech_pack__style_no", "tracking_no"]
    readonly_fields = ["status", "round", "buyer_comments"]
    inlines = [SampleMeasurementInline]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["doc_type", "doc_id", "action", "user", "created_at"]
    list_filter = ["doc_type", "action"]
