from django.core.management import call_command
from django.test import TestCase

from .models import User


class CreateSuperuserTests(TestCase):
    def test_createsuperuser_command_gives_admin_role(self):
        call_command("createsuperuser", "--noinput", username="owner", email="o@example.com", verbosity=0)
        self.assertEqual(User.objects.get(username="owner").role, User.Role.ADMIN)

    def test_normal_users_still_default_to_sales(self):
        self.assertEqual(User.objects.create_user("staff", password="pass12345!").role, User.Role.SALES)
