"""
Read-only ERP reports. All numbers are aggregated in PostgreSQL.

Only orders with status confirmed / invoiced / paid count as sales.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce, ExtractMonth
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.billing.models import Invoice
from apps.companies.models import Company
from apps.ddp.models import Shipment
from apps.employees.models import Employee
from apps.sales.models import SalesOrder

ZERO = Decimal("0")
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _int_param(request, name, default, lo, hi):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError({name: "Must be a whole number."})
    if not lo <= value <= hi:
        raise ValidationError({name: f"Must be between {lo} and {hi}."})
    return value


def _company_param(request):
    raw = request.query_params.get("company")
    if not raw:
        return None
    if not raw.isdigit():
        raise ValidationError({"company": "Must be a company id."})
    return int(raw)


def _revenue_orders(request):
    qs = SalesOrder.objects.filter(status__in=SalesOrder.REVENUE_STATUSES)
    company = _company_param(request)
    if company:
        qs = qs.filter(company_id=company)
    return qs


def _month_range(year, month):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


@api_view(["GET"])
def dashboard(request):
    """Key numbers for the dashboard home page."""
    today = timezone.localdate()
    orders = _revenue_orders(request)
    this_start, this_end = _month_range(today.year, today.month)
    prev_year, prev_month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    prev_start, prev_end = _month_range(prev_year, prev_month)

    totals = orders.aggregate(
        this_month=Coalesce(Sum("total", filter=Q(order_date__gte=this_start, order_date__lt=this_end)), ZERO),
        last_month=Coalesce(Sum("total", filter=Q(order_date__gte=prev_start, order_date__lt=prev_end)), ZERO),
        year_to_date=Coalesce(Sum("total", filter=Q(order_date__year=today.year)), ZERO),
        orders_this_month=Count("id", filter=Q(order_date__gte=this_start, order_date__lt=this_end)),
    )
    growth = None
    if totals["last_month"]:
        growth = round(float((totals["this_month"] - totals["last_month"]) / totals["last_month"] * 100), 1)

    company = _company_param(request)
    open_invoices = Invoice.objects.filter(status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID])
    if company:
        open_invoices = open_invoices.filter(company_id=company)
    receivables = open_invoices.aggregate(
        outstanding=Coalesce(Sum(F("total") - F("amount_paid")), ZERO),
        overdue=Coalesce(Sum(F("total") - F("amount_paid"), filter=Q(due_date__lt=today)), ZERO),
        overdue_count=Count("id", filter=Q(due_date__lt=today)),
    )
    employees = Employee.objects.filter(status=Employee.Status.ACTIVE)
    shipments = Shipment.objects.exclude(status__in=[Shipment.Status.DELIVERED, Shipment.Status.CANCELLED])
    if company:
        employees = employees.filter(company_id=company)
        shipments = shipments.filter(company_id=company)

    return Response({
        "month": f"{MONTH_NAMES[today.month - 1]} {today.year}",
        "sales_this_month": totals["this_month"],
        "sales_last_month": totals["last_month"],
        "growth_percent": growth,
        "sales_year_to_date": totals["year_to_date"],
        "orders_this_month": totals["orders_this_month"],
        "active_employees": employees.count(),
        "companies": Company.objects.filter(is_active=True).count(),
        "open_ddp_shipments": shipments.count(),
        "outstanding_receivables": receivables["outstanding"],
        "overdue_receivables": receivables["overdue"],
        "overdue_invoices": receivables["overdue_count"],
    })


@api_view(["GET"])
def monthly_sales(request):
    """Total sales for each month of a year (all 12 months, zeros included)."""
    year = _int_param(request, "year", timezone.localdate().year, 2000, 2100)
    rows = (
        _revenue_orders(request)
        .filter(order_date__year=year)
        .annotate(month=ExtractMonth("order_date"))
        .values("month")
        .annotate(total=Sum("total"), orders=Count("id"))
    )
    by_month = {r["month"]: r for r in rows}
    data = [
        {
            "month": m,
            "label": MONTH_NAMES[m - 1],
            "total": by_month.get(m, {}).get("total") or ZERO,
            "orders": by_month.get(m, {}).get("orders") or 0,
        }
        for m in range(1, 13)
    ]
    return Response({"year": year, "grand_total": sum(d["total"] for d in data), "months": data})


@api_view(["GET"])
def employee_sales(request):
    """Sales per employee for one month, compared with their monthly target."""
    today = timezone.localdate()
    year = _int_param(request, "year", today.year, 2000, 2100)
    month = _int_param(request, "month", today.month, 1, 12)
    start, end = _month_range(year, month)
    month_filter = Q(
        sales_orders__status__in=SalesOrder.REVENUE_STATUSES,
        sales_orders__order_date__gte=start,
        sales_orders__order_date__lt=end,
    )
    employees = Employee.objects.select_related("company").exclude(status=Employee.Status.EXITED)
    company = _company_param(request)
    if company:
        employees = employees.filter(company_id=company)
    employees = employees.annotate(
        sales=Coalesce(Sum("sales_orders__total", filter=month_filter), ZERO),
        orders=Count("sales_orders", filter=month_filter),
    ).order_by("-sales")

    data = []
    for e in employees:
        target = e.monthly_sales_target
        data.append({
            "employee_id": e.id,
            "employee_code": e.employee_code,
            "name": e.full_name,
            "company": e.company.name,
            "sales": e.sales,
            "orders": e.orders,
            "target": target,
            "achievement_percent": round(float(e.sales / target * 100), 1) if target else None,
        })
    return Response({"year": year, "month": month, "label": f"{MONTH_NAMES[month - 1]} {year}", "employees": data})


@api_view(["GET"])
def company_sales(request):
    """Sales per company per month for a year — a company-wise overview."""
    year = _int_param(request, "year", timezone.localdate().year, 2000, 2100)
    rows = (
        SalesOrder.objects.filter(status__in=SalesOrder.REVENUE_STATUSES, order_date__year=year)
        .annotate(month=ExtractMonth("order_date"))
        .values("company_id", "month")
        .annotate(total=Sum("total"))
    )
    lookup = {(r["company_id"], r["month"]): r["total"] for r in rows}
    data = []
    for c in Company.objects.order_by("name"):
        months = [lookup.get((c.id, m), ZERO) for m in range(1, 13)]
        data.append({"company_id": c.id, "company": c.name, "months": months, "total": sum(months)})
    return Response({"year": year, "month_labels": MONTH_NAMES, "companies": data})
