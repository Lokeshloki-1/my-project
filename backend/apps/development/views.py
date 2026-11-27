from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.buyers.services import Conflict

from . import services
from .models import Sample, TechPack
from .serializers import SampleListSerializer, SampleSerializer, TechPackListSerializer, TechPackSerializer


class _DocViewSet(viewsets.GenericViewSet):
    list_serializer = None
    detail_serializer = None

    def get_serializer_class(self):
        return self.list_serializer if self.action == "list" else self.detail_serializer

    def _detail(self, obj, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=obj.pk)
        return Response(self.detail_serializer(fresh, context={"request": self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._detail(serializer.save(), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return self._detail(serializer.save())


class TechPackViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = TechPack.objects.select_related("buyer", "released_by", "cost_sheet").prefetch_related("measurements", "bom")
    list_serializer = TechPackListSerializer
    detail_serializer = TechPackSerializer
    filterset_fields = ["company", "buyer", "status", "category", "season", "production_approved"]
    search_fields = ["tp_no", "style_no", "style_name", "season", "buyer__legal_name"]
    ordering_fields = ["created_at", "updated_at", "style_no"]

    def perform_destroy(self, instance):
        if instance.status != TechPack.Status.DRAFT or instance.previous_id:
            raise Conflict("Only a first draft without samples can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        return self._detail(services.release_tech_pack(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        new = services.revise_tech_pack(self.get_object(), request.user, str(request.data.get("note", "")).strip())
        return self._detail(new, status.HTTP_201_CREATED)


class SampleViewSet(_DocViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                    mixins.UpdateModelMixin, mixins.DestroyModelMixin):
    queryset = Sample.objects.select_related("buyer", "tech_pack", "previous", "resubmission").prefetch_related(
        "measurements__measurement"
    )
    list_serializer = SampleListSerializer
    detail_serializer = SampleSerializer
    filterset_fields = {
        "company": ["exact"], "buyer": ["exact"], "tech_pack": ["exact"], "status": ["exact", "in"],
        "sample_type": ["exact"], "due_date": ["lte", "gte"],
    }
    search_fields = ["sample_no", "tech_pack__style_no", "tech_pack__style_name", "buyer__legal_name", "tracking_no"]
    ordering_fields = ["created_at", "due_date", "requested_on"]

    def perform_destroy(self, instance):
        if instance.status != Sample.Status.REQUESTED:
            raise Conflict("Only samples not yet started can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._detail(services.start_sample(self.get_object(), request.user))

    @action(detail=True, methods=["post"], url_path="mark-ready")
    def mark_ready(self, request, pk=None):
        return self._detail(services.mark_ready(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        d = request.data
        sample = services.send_sample(
            self.get_object(), request.user, str(d.get("courier", "")).strip(), str(d.get("tracking_no", "")).strip(),
            d.get("sent_on") or None,
        )
        return self._detail(sample)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        sample = services.decide_sample(
            self.get_object(), request.user, str(request.data.get("decision", "")), str(request.data.get("comments", "")).strip()
        )
        return self._detail(sample)

    @action(detail=True, methods=["post"])
    def resubmit(self, request, pk=None):
        new = services.resubmit_sample(self.get_object(), request.user, str(request.data.get("instructions", "")).strip())
        return self._detail(new, status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"])
    def measurements(self, request, pk=None):
        readings = request.data.get("readings", []) if isinstance(request.data, dict) else request.data
        return self._detail(services.record_measurements(self.get_object(), request.user, readings))

    @action(detail=False, methods=["get"])
    def board(self, request):
        """Count of samples per status (respects the list filters)."""
        qs = self.filter_queryset(Sample.objects.all())
        counts = {r["status"]: r["n"] for r in qs.order_by().values("status").annotate(n=Count("id"))}
        return Response([{"status": v, "label": label, "count": counts.get(v, 0)} for v, label in Sample.Status.choices])
