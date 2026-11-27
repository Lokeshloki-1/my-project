from django.db import transaction
from rest_framework import serializers

from . import services
from .models import Buyer, BuyerContact, BuyerEnquiry, BuyerRequirement, BuyerStatusLog, CreditCheck


def _user_name(user):
    return (user.get_full_name() or user.username) if user else None


class BuyerEnquirySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    buyer_id = serializers.IntegerField(source="buyer.id", read_only=True, default=None)

    class Meta:
        model = BuyerEnquiry
        fields = [
            "id", "enquiry_no", "company", "company_name", "source", "buyer_name", "contact_name", "email", "phone",
            "country", "product_interest", "expected_volume", "received_on", "assigned_to", "assigned_to_name",
            "status", "reject_reason", "notes", "buyer_id", "created_at", "updated_at",
        ]
        read_only_fields = ["enquiry_no", "reject_reason", "created_at", "updated_at"]

    def get_assigned_to_name(self, obj):
        return _user_name(obj.assigned_to)

    def validate_status(self, value):
        # Converted / rejected are set by the convert and reject actions.
        current = getattr(self.instance, "status", BuyerEnquiry.Status.NEW)
        if value != current and value not in (BuyerEnquiry.Status.NEW, BuyerEnquiry.Status.QUALIFIED):
            raise serializers.ValidationError("Use the Convert or Reject action for this.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.status in (BuyerEnquiry.Status.CONVERTED, BuyerEnquiry.Status.REJECTED):
            raise services.Conflict(f"Enquiry is {self.instance.get_status_display().lower()} and can no longer be edited.")
        if self.instance and "company" in attrs and attrs["company"] != self.instance.company:
            raise serializers.ValidationError({"company": "The company of an enquiry cannot be changed."})
        return attrs


class BuyerContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerContact
        fields = ["id", "buyer", "name", "designation", "department", "email", "phone", "is_primary"]
        # The one-primary-per-buyer rule is kept by save() (it demotes the old primary first)
        # and enforced by the database constraint, so skip DRF's auto unique validator.
        validators = []

    def validate(self, attrs):
        buyer = attrs.get("buyer", getattr(self.instance, "buyer", None))
        if self.instance and buyer != self.instance.buyer:
            raise serializers.ValidationError({"buyer": "A contact cannot be moved to another buyer."})
        services.ensure_editable(buyer, self.context["request"].user)
        email = attrs.get("email", getattr(self.instance, "email", ""))
        phone = attrs.get("phone", getattr(self.instance, "phone", ""))
        if not email and not phone:
            raise serializers.ValidationError("Give an email or a phone number.")
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        buyer = self.validated_data.get("buyer", getattr(self.instance, "buyer", None))
        make_primary = self.validated_data.get("is_primary", getattr(self.instance, "is_primary", False))
        others = buyer.contacts.exclude(pk=getattr(self.instance, "pk", None))
        if make_primary:
            others.filter(is_primary=True).update(is_primary=False)
        elif not others.filter(is_primary=True).exists():
            # The first contact becomes primary automatically.
            self.validated_data["is_primary"] = True
        return super().save(**kwargs)


class BuyerRequirementSerializer(serializers.ModelSerializer):
    product_categories = serializers.ListField(
        child=serializers.ChoiceField(choices=BuyerRequirement.Category.choices), required=False, allow_empty=True
    )
    certifications = serializers.ListField(
        child=serializers.ChoiceField(choices=BuyerRequirement.Certification.choices), required=False, allow_empty=True
    )

    class Meta:
        model = BuyerRequirement
        fields = [
            "id", "buyer", "product_categories", "fabric_composition", "gsm_min", "gsm_max", "size_range",
            "annual_volume", "target_price_min", "target_price_max", "price_currency", "certifications",
            "packaging", "labelling", "testing_lab", "delivery_port", "payment_terms_requested", "notes", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        buyer = attrs.get("buyer", getattr(self.instance, "buyer", None))
        if self.instance and buyer != self.instance.buyer:
            raise serializers.ValidationError({"buyer": "Requirements cannot be moved to another buyer."})
        services.ensure_editable(buyer, self.context["request"].user)
        for low, high, label in [("gsm_min", "gsm_max", "GSM"), ("target_price_min", "target_price_max", "Target price")]:
            lo = attrs.get(low, getattr(self.instance, low, None))
            hi = attrs.get(high, getattr(self.instance, high, None))
            if lo is not None and hi is not None and lo > hi:
                raise serializers.ValidationError({high: f"{label} maximum must be at least the minimum."})
        for field in ("product_categories", "certifications"):
            if field in attrs:
                attrs[field] = list(dict.fromkeys(attrs[field]))  # drop duplicates, keep order
        return attrs


class CreditCheckSerializer(serializers.ModelSerializer):
    checked_by_name = serializers.SerializerMethodField()
    requested_limit = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=0, required=False)
    approved_limit = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=0, required=False)

    class Meta:
        model = CreditCheck
        fields = [
            "id", "buyer", "requested_limit", "approved_limit", "currency", "payment_terms", "risk_rating",
            "bank_reference", "trade_references", "ecgc_cover", "result", "remarks",
            "checked_by", "checked_by_name", "checked_at",
        ]
        read_only_fields = ["checked_by", "checked_at"]

    def get_checked_by_name(self, obj):
        return _user_name(obj.checked_by)

    def validate(self, attrs):
        if attrs["result"] == CreditCheck.Result.FAIL:
            attrs["approved_limit"] = 0
        elif not attrs.get("approved_limit"):
            raise serializers.ValidationError({"approved_limit": "Give the approved credit limit for a passed check."})
        return attrs

    def create(self, validated_data):
        buyer = validated_data.pop("buyer")
        return services.record_credit_check(buyer, self.context["request"].user, **validated_data)


class BuyerStatusLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = BuyerStatusLog
        fields = ["id", "from_status", "to_status", "note", "user", "user_name", "created_at"]

    def get_user_name(self, obj):
        return _user_name(obj.user)


class BuyerSerializer(serializers.ModelSerializer):
    """List and create/update shape."""

    company_name = serializers.CharField(source="company.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    enquiry_no = serializers.CharField(source="enquiry.enquiry_no", read_only=True, default=None)
    customer_id = serializers.IntegerField(read_only=True)
    primary_contact = serializers.SerializerMethodField()

    class Meta:
        model = Buyer
        fields = [
            "id", "buyer_code", "company", "company_name", "enquiry", "enquiry_no", "legal_name", "trade_name",
            "buyer_type", "country", "city", "address", "tax_id", "website", "year_established", "annual_turnover",
            "preferred_currency", "default_incoterm", "bank_name", "notes",
            "status", "status_label", "rejection_reason", "approved_by", "approved_at", "customer_id",
            "primary_contact", "created_at", "updated_at",
        ]
        read_only_fields = [
            "buyer_code", "enquiry", "status", "rejection_reason", "approved_by", "approved_at", "created_at", "updated_at",
        ]

    def get_primary_contact(self, obj):
        primary = next((c for c in obj.contacts.all() if c.is_primary), None)
        return {"name": primary.name, "email": primary.email, "phone": primary.phone} if primary else None

    def validate(self, attrs):
        if self.instance:
            services.ensure_editable(self.instance, self.context["request"].user)
            if "company" in attrs and attrs["company"] != self.instance.company:
                raise serializers.ValidationError({"company": "The company of a buyer cannot be changed."})
        if "preferred_currency" in attrs:
            attrs["preferred_currency"] = attrs["preferred_currency"].upper()
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        buyer = Buyer.objects.create(created_by=user, **validated_data)
        services.log_created(buyer, user)
        return buyer


class BuyerDetailSerializer(BuyerSerializer):
    """Single buyer with everything the onboarding screen needs."""

    contacts = BuyerContactSerializer(many=True, read_only=True)
    requirement = serializers.SerializerMethodField()
    latest_credit_check = serializers.SerializerMethodField()
    onboarding = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta(BuyerSerializer.Meta):
        fields = BuyerSerializer.Meta.fields + [
            "contacts", "requirement", "latest_credit_check", "onboarding", "allowed_actions", "approved_by_name",
        ]

    def get_requirement(self, obj):
        req = services._requirement(obj)
        return BuyerRequirementSerializer(req, context=self.context).data if req else None

    def get_latest_credit_check(self, obj):
        check = services._latest_credit_check(obj)
        return CreditCheckSerializer(check, context=self.context).data if check else None

    def get_onboarding(self, obj):
        return services.onboarding_steps(obj)

    def get_allowed_actions(self, obj):
        return services.allowed_actions(obj, self.context["request"].user)

    def get_approved_by_name(self, obj):
        return _user_name(obj.approved_by)
