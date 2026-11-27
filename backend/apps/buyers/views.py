from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsCreditReviewerOrReadOnly

from . import services
from .models import Buyer, BuyerContact, BuyerEnquiry, BuyerRequirement, CreditCheck
from .serializers import (
    BuyerContactSerializer,
    BuyerDetailSerializer,
    BuyerEnquirySerializer,
    BuyerRequirementSerializer,
    BuyerSerializer,
    BuyerStatusLogSerializer,
    CreditCheckSerializer,
)


def _reason(request):
    return str(request.data.get("reason", "")).strip()


class BuyerEnquiryViewSet(viewsets.ModelViewSet):
    queryset = BuyerEnquiry.objects.select_related("company", "assigned_to", "buyer")
    serializer_class = BuyerEnquirySerializer
    filterset_fields = ["company", "status", "source", "country", "assigned_to"]
    search_fields = ["enquiry_no", "buyer_name", "contact_name", "email", "country", "product_interest"]
    ordering_fields = ["received_on", "created_at", "expected_volume"]

    def perform_destroy(self, instance):
        if instance.status == BuyerEnquiry.Status.CONVERTED:
            raise services.Conflict("A converted enquiry cannot be deleted; it is linked to a buyer.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        buyer, created = services.convert_enquiry(self.get_object(), request.user)
        data = BuyerDetailSerializer(_buyer_queryset().get(pk=buyer.pk), context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        enquiry = services.reject_enquiry(self.get_object(), request.user, _reason(request))
        return Response(self.get_serializer(enquiry).data)


def _buyer_queryset():
    return Buyer.objects.select_related("company", "enquiry", "approved_by", "requirement").prefetch_related(
        "contacts", "credit_checks__checked_by"
    )


class BuyerViewSet(viewsets.ModelViewSet):
    queryset = _buyer_queryset()
    filterset_fields = ["company", "status", "country", "buyer_type"]
    search_fields = ["buyer_code", "legal_name", "trade_name", "country", "city", "contacts__name", "contacts__email"]
    ordering_fields = ["created_at", "legal_name", "updated_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Searching across contacts can repeat a buyer once per matching contact.
        return qs.distinct() if self.request.query_params.get("search") else qs

    def get_serializer_class(self):
        return BuyerSerializer if self.action == "list" else BuyerDetailSerializer

    def _detail(self, buyer, code=status.HTTP_200_OK):
        fresh = _buyer_queryset().get(pk=buyer.pk)
        return Response(BuyerDetailSerializer(fresh, context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        buyer = serializer.save()
        return self._detail(buyer, status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.status != Buyer.Status.REGISTERED:
            raise services.Conflict("Only registered buyers can be deleted. Reject the buyer instead.")
        if instance.credit_checks.exists():
            raise services.Conflict("This buyer has credit check history and cannot be deleted. Reject it instead.")
        enquiry = instance.enquiry
        instance.delete()
        if enquiry:  # Put the enquiry back so it can be converted again.
            enquiry.status = BuyerEnquiry.Status.QUALIFIED
            enquiry.save(update_fields=["status", "updated_at"])

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._detail(services.submit_buyer(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._detail(services.approve_buyer(self.get_object(), request.user, _reason(request)))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._detail(services.reject_buyer(self.get_object(), request.user, _reason(request)))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._detail(services.reopen_buyer(self.get_object(), request.user, _reason(request)))

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        logs = self.get_object().status_logs.select_related("user")
        return Response(BuyerStatusLogSerializer(logs, many=True).data)

    @action(detail=False, methods=["get"])
    def pipeline(self, request):
        """Number of buyers in each status (respects the same filters as the list)."""
        qs = self.filter_queryset(Buyer.objects.all())
        counts = {row["status"]: row["n"] for row in qs.order_by().values("status").annotate(n=Count("id"))}
        stages = [
            {"status": value, "label": label, "count": counts.get(value, 0)} for value, label in Buyer.Status.choices
        ]
        open_enquiries = BuyerEnquiry.objects.filter(
            status__in=[BuyerEnquiry.Status.NEW, BuyerEnquiry.Status.QUALIFIED]
        )
        if request.query_params.get("company"):
            open_enquiries = open_enquiries.filter(company=request.query_params["company"])
        return Response({"stages": stages, "total": sum(counts.values()), "open_enquiries": open_enquiries.count()})


class BuyerContactViewSet(viewsets.ModelViewSet):
    queryset = BuyerContact.objects.select_related("buyer")
    serializer_class = BuyerContactSerializer
    filterset_fields = ["buyer", "department", "is_primary"]
    search_fields = ["name", "email", "phone", "designation"]

    def perform_destroy(self, instance):
        services.ensure_editable(instance.buyer, self.request.user)
        was_primary = instance.is_primary
        buyer = instance.buyer
        instance.delete()
        if was_primary:  # Promote another contact so the buyer keeps a primary one.
            nxt = buyer.contacts.order_by("id").first()
            if nxt:
                nxt.is_primary = True
                nxt.save(update_fields=["is_primary"])


class BuyerRequirementViewSet(viewsets.ModelViewSet):
    queryset = BuyerRequirement.objects.select_related("buyer")
    serializer_class = BuyerRequirementSerializer
    filterset_fields = ["buyer"]

    def perform_destroy(self, instance):
        services.ensure_editable(instance.buyer, self.request.user)
        instance.delete()


class CreditCheckViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Credit checks are an audit record: they can be added and read, never edited or deleted."""

    queryset = CreditCheck.objects.select_related("buyer", "checked_by")
    serializer_class = CreditCheckSerializer
    permission_classes = [IsCreditReviewerOrReadOnly]
    filterset_fields = ["buyer", "result", "risk_rating"]
