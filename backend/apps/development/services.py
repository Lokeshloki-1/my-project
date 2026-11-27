"""
Workflow for tech packs and samples. Every status change goes through a function here:
it locks the row, checks the transition and writes an ActivityLog entry.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.models import Buyer
from apps.buyers.services import Conflict, is_manager

from .models import ActivityLog, BOMItem, Sample, SampleMeasurement, TechPack

logger = logging.getLogger(__name__)
S = Sample.Status


def log(doc_type, doc, action, user, note=""):
    ActivityLog.objects.create(doc_type=doc_type, doc_id=doc.pk, action=action, user=user, note=note)
    logger.info("%s %s %s user=%s", doc_type, doc.pk, action, getattr(user, "pk", None))


def history(doc_type, doc_id):
    return ActivityLog.objects.filter(doc_type=doc_type, doc_id=doc_id).select_related("user")


def _lock(model, obj):
    return model.objects.select_for_update().get(pk=obj.pk)


def require_active_buyer(buyer):
    if buyer.status == Buyer.Status.REJECTED:
        raise ValidationError({"buyer": f"{buyer.legal_name} was rejected."})


# ---------------------------------------------------------------- tech packs

def missing_for_release(tp):
    missing = []
    if not tp.sizes:
        missing.append("Sizes for the measurement chart")
    measurements = list(tp.measurements.all())
    if not measurements:
        missing.append("At least one point of measure")
    for m in measurements:
        empty = [s for s in tp.sizes if m.values.get(s) in (None, "")]
        if empty:
            missing.append(f"“{m.point}” has no value for {', '.join(empty)}")
    if not any(b.category == BOMItem.Category.FABRIC for b in tp.bom.all()):
        missing.append("A fabric line in the bill of materials")
    return missing


def tech_pack_actions(tp, user):
    actions = []
    if tp.status == TechPack.Status.DRAFT:
        actions += ["edit", "delete"]
        if is_manager(user):
            actions.append("release")
    if tp.status == TechPack.Status.RELEASED:
        actions += ["request_sample", "revise"]
    return actions


@transaction.atomic
def release_tech_pack(tp, user):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can release tech packs.")
    tp = _lock(TechPack, tp)
    if tp.status == TechPack.Status.RELEASED:
        return tp
    if tp.status != TechPack.Status.DRAFT:
        raise Conflict("Only draft tech packs can be released.")
    missing = missing_for_release(tp)
    if missing:
        raise ValidationError({"missing": missing, "detail": "Complete the tech pack before releasing it."})
    tp.status = TechPack.Status.RELEASED
    tp.released_by = user
    tp.released_at = timezone.now()
    tp.save(update_fields=["status", "released_by", "released_at", "updated_at"])
    log("tech_pack", tp, "released", user, f"Revision {tp.revision}")
    return tp


@transaction.atomic
def revise_tech_pack(tp, user, note=""):
    """New draft revision with everything copied; the released one becomes superseded.
    Calling it again returns the same new revision."""
    tp = _lock(TechPack, tp)
    existing = TechPack.objects.filter(previous=tp).first()
    if existing:
        return existing
    if tp.status != TechPack.Status.RELEASED:
        raise Conflict("Only a released tech pack can be revised.")
    measurements, bom = list(tp.measurements.all()), list(tp.bom.all())
    fields = [
        "company_id", "buyer_id", "style_no", "style_name", "season", "category", "description",
        "fabric_composition", "gsm", "colourways", "sizes", "base_size", "construction", "wash_care",
        "packing", "cost_sheet_id",
    ]
    new = TechPack.objects.create(
        previous=tp, revision=tp.revision + 1, created_by=user, **{f: getattr(tp, f) for f in fields}
    )
    for item in measurements + bom:
        item.pk = None
        item.tech_pack = new
        item.save()
    tp.status = TechPack.Status.SUPERSEDED
    tp.save(update_fields=["status", "updated_at"])
    log("tech_pack", tp, "superseded", user, f"Replaced by revision {new.revision}")
    log("tech_pack", new, "created", user, note or f"Revision {new.revision} of {tp.tp_no}")
    return new


# ---------------------------------------------------------------- samples

def next_round(tech_pack, sample_type):
    """1 + samples of this type already made for any revision of the style."""
    return Sample.objects.filter(tech_pack__tp_no=tech_pack.tp_no, sample_type=sample_type).count() + 1


def sample_actions(sample, user):
    return {
        S.REQUESTED: ["edit", "start", "delete"],
        S.IN_PROGRESS: ["edit", "mark_ready"],
        S.READY: ["edit", "send"],
        S.SENT: ["decide"],
        S.APPROVED: [],
        S.APPROVED_WITH_COMMENTS: [] if hasattr(sample, "resubmission") else ["resubmit"],
        S.REJECTED: [] if hasattr(sample, "resubmission") else ["resubmit"],
    }[sample.status] + (["measure"] if sample.status in Sample.OPEN_STATUSES else [])


def _move(sample, allowed, to, user, note="", extra_fields=()):
    if sample.status not in allowed:
        raise Conflict(f"This sample is {sample.get_status_display().lower()}; that step is not possible now.")
    frm = sample.status
    sample.status = to
    sample.save(update_fields=["status", "updated_at", *extra_fields])
    log("sample", sample, to, user, note or f"{Sample.Status(frm).label} → {Sample.Status(to).label}")
    return sample


@transaction.atomic
def start_sample(sample, user):
    return _move(_lock(Sample, sample), [S.REQUESTED], S.IN_PROGRESS, user)


@transaction.atomic
def mark_ready(sample, user):
    return _move(_lock(Sample, sample), [S.IN_PROGRESS], S.READY, user)


@transaction.atomic
def send_sample(sample, user, courier, tracking_no, sent_on=None):
    sample = _lock(Sample, sample)
    if not courier:
        raise ValidationError({"courier": "Give the courier, e.g. DHL."})
    sample.courier, sample.tracking_no = courier, tracking_no
    sample.sent_on = sent_on or timezone.localdate()
    note = f"Sent by {courier}" + (f", tracking {tracking_no}" if tracking_no else "")
    return _move(sample, [S.READY], S.SENT, user, note, ("courier", "tracking_no", "sent_on"))


@transaction.atomic
def decide_sample(sample, user, decision, comments):
    if decision not in (S.APPROVED, S.APPROVED_WITH_COMMENTS, S.REJECTED):
        raise ValidationError({"decision": "Choose approved, approved_with_comments or rejected."})
    if decision != S.APPROVED and not comments:
        raise ValidationError({"comments": "Write down the buyer's comments."})
    sample = _lock(Sample, sample)
    sample.buyer_comments = comments
    sample.decided_on = timezone.localdate()
    _move(sample, [S.SENT], decision, user, comments or "Approved by buyer", ("buyer_comments", "decided_on"))
    if sample.sample_type == Sample.Type.PP and decision in Sample.APPROVED_STATUSES:
        tp = _lock(TechPack, sample.tech_pack)
        if not tp.production_approved:
            tp.production_approved = True
            tp.production_approved_at = timezone.now()
            tp.save(update_fields=["production_approved", "production_approved_at", "updated_at"])
            log("tech_pack", tp, "approved_for_production", user, f"PP sample {sample.sample_no} approved")
    return sample


@transaction.atomic
def resubmit_sample(sample, user, instructions=""):
    """Next round of the same sample type. Calling it again returns the same new sample."""
    sample = _lock(Sample, sample)
    existing = Sample.objects.filter(previous=sample).first()
    if existing:
        return existing
    if sample.status not in (S.REJECTED, S.APPROVED_WITH_COMMENTS):
        raise Conflict("Only rejected samples or samples approved with comments get another round.")
    tp = sample.tech_pack
    if tp.status == tp.Status.SUPERSEDED:
        tp = TechPack.objects.filter(tp_no=tp.tp_no, status=TechPack.Status.RELEASED).first() or tp
    new = Sample.objects.create(
        company=sample.company, tech_pack=tp, buyer=sample.buyer, sample_type=sample.sample_type,
        round=next_round(tp, sample.sample_type), previous=sample, colourway=sample.colourway, size=sample.size,
        quantity=sample.quantity, requested_on=timezone.localdate(), created_by=user,
        instructions=instructions or f"Corrections from round {sample.round}: {sample.buyer_comments}",
    )
    log("sample", new, "requested", user, f"Round {new.round}, after {sample.sample_no}")
    return new


@transaction.atomic
def record_measurements(sample, user, readings):
    """Replace the sample's measurements. readings = [{"measurement": id, "actual": "50.5"}, ...]"""
    sample = _lock(Sample, sample)
    if sample.status not in Sample.OPEN_STATUSES:
        raise Conflict("Measurements can only be recorded before the buyer's decision.")
    if not sample.size:
        raise ValidationError({"size": "Set the sample size before measuring."})
    points = {m.id: m for m in sample.tech_pack.measurements.all()}
    rows = []
    for r in readings:
        m = points.get(int(r.get("measurement") or 0))
        if m is None:
            raise ValidationError({"measurements": "A point of measure is not on this sample's tech pack."})
        if r.get("actual") in (None, ""):
            continue
        spec = m.values.get(sample.size)
        if spec in (None, ""):
            raise ValidationError({"measurements": f"“{m.point}” has no spec for size {sample.size}."})
        try:
            actual = Decimal(str(r["actual"]))
        except InvalidOperation:
            raise ValidationError({"measurements": f"“{r['actual']}” is not a number."}) from None
        rows.append(SampleMeasurement(sample=sample, measurement=m, spec=Decimal(str(spec)), tolerance=m.tolerance, actual=actual))
    sample.measurements.all().delete()
    SampleMeasurement.objects.bulk_create(rows)
    failed = sum(1 for r in rows if not r.within_tolerance)
    log("sample", sample, "measured", user, f"{len(rows)} points, {failed} out of tolerance")
    return sample


def measurement_summary(sample):
    rows = list(sample.measurements.all())
    failed = [r for r in rows if not r.within_tolerance]
    return {"measured": len(rows), "out_of_tolerance": len(failed), "passed": bool(rows) and not failed}
