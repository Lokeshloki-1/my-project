from rest_framework import serializers

from .models import Company


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id", "name", "code", "tax_id", "email", "phone", "address",
            "city", "country", "currency", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
