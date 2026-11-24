from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="report-dashboard"),
    path("monthly-sales/", views.monthly_sales, name="report-monthly-sales"),
    path("employee-sales/", views.employee_sales, name="report-employee-sales"),
    path("company-sales/", views.company_sales, name="report-company-sales"),
]
