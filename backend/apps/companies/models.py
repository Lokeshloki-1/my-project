from django.db import models


class Company(models.Model):
    """A business entity running on Hazpo (the ERP supports several companies)."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True, help_text="Short code, e.g. HZP-IN")
    tax_id = models.CharField("GSTIN / Tax ID", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India")
    currency = models.CharField(max_length=3, default="INR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return f"{self.code} - {self.name}"
