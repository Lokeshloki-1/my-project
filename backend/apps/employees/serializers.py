from rest_framework import serializers

from .models import Department, Employee


class DepartmentSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Department
        fields = ["id", "company", "company_name", "name"]


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = [
            "id", "company", "company_name", "department", "department_name", "user",
            "employee_code", "first_name", "last_name", "full_name", "email", "phone",
            "designation", "date_joined", "monthly_salary", "monthly_sales_target",
            "status", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        company = attrs.get("company", getattr(self.instance, "company", None))
        department = attrs.get("department", getattr(self.instance, "department", None))
        if department and company and department.company_id != company.id:
            raise serializers.ValidationError({"department": "Department belongs to a different company."})
        return attrs
