from datetime import date, timedelta

from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsManagerOrReadOnly
from apps.buyers.services import Conflict

from . import aql, services
from .models import CorrectiveAction, DefectType, FinalInspection, InlineInspection
from .serializers import (
    CorrectiveActionSerializer,
    DefectTypeSerializer,
    FinalInspectionListSerializer,
    FinalInspectionSerializer,
    InlineInspectionSerializer,
)


def _date(value, default):
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        raise ValidationError({"date": "Use YYYY-MM-DD."}) from None


class DefectTypeViewSet(viewsets.ModelViewSet):
    queryset = DefectType.objects.all()
    serializer_class = DefectTypeSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["company", "category", "severity", "is_active"]
    search_fields = ["code", "name"]

    def perform_destroy(self, instance):
        if instance.inline_defects.exists() or instance.final_defects.exists():
            raise Conflict("This defect type has been recorded. Mark it inactive instead.")
        instance.delete()


class InlineInspectionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Inline checks are a record of what was found: created, never edited."""

    queryset = InlineInspection.objects.select_related("production_order", "line", "inspector").prefetch_related("defects__defect_type")
    serializer_class = InlineInspectionSerializer
    filterset_fields = {"company": ["exact"], "production_order": ["exact"], "line": ["exact"], "result": ["exact"],
                        "date": ["exact", "gte", "lte"]}
    search_fields = ["production_order__wo_no", "production_order__style_no", "operation", "operator"]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        insp = s.save()
        return Response(self.get_serializer(self.get_queryset().get(pk=insp.pk)).data, status=status.HTTP_201_CREATED)


class FinalInspectionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                             mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = FinalInspection.objects.select_related("production_order__order__buyer", "inspector").prefetch_related(
        "defects__defect_type", "production_order__entries")
    filterset_fields = {"company": ["exact"], "production_order": ["exact"], "status": ["exact"], "inspection_date": ["gte", "lte"]}
    search_fields = ["fi_no", "production_order__wo_no", "production_order__style_no", "inspected_by_party"]

    def get_serializer_class(self):
        return FinalInspectionListSerializer if self.action == "list" else FinalInspectionSerializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        return Response(FinalInspectionSerializer(self.get_queryset().get(pk=obj.pk), context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._detail(s.save(), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        s = self.get_serializer(self.get_object(), data=request.data, partial=kwargs.pop("partial", False))
        s.is_valid(raise_exception=True)
        return self._detail(s.save())

    def perform_destroy(self, instance):
        if instance.status != FinalInspection.Status.DRAFT:
            raise Conflict("Completed inspections are kept on record.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._detail(services.submit_final(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reinspect(self, request, pk=None):
        return self._detail(services.reinspect(self.get_object(), request.user), status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def plan(self, request):
        """AQL sample size and accept numbers for a lot size (live while filling the form)."""
        try:
            lot = int(request.query_params.get("lot_size") or 0)
        except ValueError:
            lot = 0
        return Response({**services.build_plan(lot, request.query_params.get("aql_major", "2.5"),
                                               request.query_params.get("aql_minor", "4.0")), "aql_choices": aql.AQL_CHOICES})


class CorrectiveActionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                              mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = CorrectiveAction.objects.select_related("production_order", "closed_by")
    serializer_class = CorrectiveActionSerializer
    filterset_fields = ["company", "status", "source", "production_order"]
    search_fields = ["problem", "root_cause", "action", "owner", "production_order__style_no"]

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        capa = services.close_capa(self.get_object(), request.user, request.data.get("root_cause", ""), request.data.get("action", ""))
        return Response(self.get_serializer(capa).data)


class QualitySummaryViewSet(viewsets.ViewSet):
    def list(self, request):
        today = timezone.localdate()
        d_to = _date(request.query_params.get("to"), today)
        d_from = _date(request.query_params.get("from"), d_to - timedelta(days=29))
        return Response(services.summary(d_from, d_to, request.query_params.get("company") or None))
