from django.conf import settings
from django.db import models
from django.db.models import Q


class Department(models.Model):
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="departments")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["company", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_department_per_company"),
        ]

    def __str__(self):
        return f"{self.name} ({self.company.code})"


class Employee(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        EXITED = "exited", "Exited"

    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT, related_name="employees")
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employee", help_text="Optional login account for this employee",
    )
    employee_code = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    date_joined = models.DateField()
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monthly_sales_target = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.CheckConstraint(condition=Q(monthly_salary__gte=0), name="employee_salary_non_negative"),
            models.CheckConstraint(condition=Q(monthly_sales_target__gte=0), name="employee_target_non_negative"),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.employee_code} - {self.full_name}"
