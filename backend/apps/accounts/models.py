from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Login account. The role decides what the user may change in the ERP."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        SALES = "sales", "Sales Executive"
        ACCOUNTANT = "accountant", "Accountant"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SALES)

    @property
    def is_manager_or_admin(self):
        return self.is_superuser or self.role in (self.Role.ADMIN, self.Role.MANAGER)
