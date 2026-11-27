from django.contrib import admin

from .models import CorrectiveAction, DefectType, FinalDefect, FinalInspection, InlineDefect, InlineInspection


@admin.register(DefectType)
class DefectTypeAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "category", "severity", "is_active"]
    list_filter = ["category", "severity", "company"]


class InlineDefectInline(admin.TabularInline):
    model = InlineDefect
    extra = 0


@admin.register(InlineInspection)
class InlineInspectionAdmin(admin.ModelAdmin):
    list_display = ["date", "line", "production_order", "pieces_checked", "total_defects", "dhu", "result"]
    list_filter = ["result", "line"]
    readonly_fields = ["total_defects", "dhu", "result"]
    inlines = [InlineDefectInline]


class FinalDefectInline(admin.TabularInline):
    model = FinalDefect
    extra = 0


@admin.register(FinalInspection)
class FinalInspectionAdmin(admin.ModelAdmin):
    list_display = ["fi_no", "production_order", "round", "lot_size", "sample_size", "major_found", "minor_found", "status"]
    list_filter = ["status"]
    readonly_fields = ["status", "code_letter", "sample_size", "accept_major", "accept_minor", "fail_reasons"]
    inlines = [FinalDefectInline]


@admin.register(CorrectiveAction)
class CorrectiveActionAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "production_order", "owner", "due_date", "status"]
    list_filter = ["status", "source"]
    readonly_fields = ["status", "closed_by", "closed_at"]
