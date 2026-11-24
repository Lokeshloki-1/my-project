from django.contrib import admin

from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "city", "country", "currency", "is_active")
    search_fields = ("name", "code")
    list_filter = ("is_active", "country")
