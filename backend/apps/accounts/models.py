from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class HazpoUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # `manage.py createsuperuser` makes the business owner's login: give it the admin role, not the default.
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Login account. The role decides what the user may change in the ERP."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        SALES = "sales", "Sales Executive"
        ACCOUNTANT = "accountant", "Accountant"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SALES)

    objects = HazpoUserManager()

    @property
    def is_manager_or_admin(self):
        return self.is_superuser or self.role in (self.Role.ADMIN, self.Role.MANAGER)
