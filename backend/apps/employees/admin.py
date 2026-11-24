from django.contrib import admin

from .models import Department, Employee


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "company")
    list_filter = ("company",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "full_name", "company", "department", "designation", "status")
    list_filter = ("company", "department", "status")
    search_fields = ("employee_code", "first_name", "last_name", "email")
