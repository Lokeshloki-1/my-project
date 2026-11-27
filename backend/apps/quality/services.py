import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.services import Conflict, is_manager
from apps.production.models import ProductionOrder
from apps.production.services import totals as wo_totals

from . import aql
from .models import (
    CorrectiveAction,
    DefectType,
    FinalDefect,
    FinalInspection,
    InlineDefect,
    InlineInspection,
    Severity,
)

logger = logging.getLogger(__name__)
R = InlineInspection.Result


def classify(dhu):
    if dhu <= InlineInspection.GREEN_MAX_DHU:
        return R.GREEN
    return R.AMBER if dhu <= InlineInspection.AMBER_MAX_DHU else R.RED


def _check_defect_types(company, defect_types):
    for dt in defect_types:
        if dt.company_id != company.id or not dt.is_active:
            raise ValidationError({"defects": f"{dt} is not an active defect type of this company."})


# ---------------------------------------------------------------- inline QC

@transaction.atomic
def create_inline(user, wo, line, data, defects):
    """defects = [(DefectType, count)]"""
    if wo.status != ProductionOrder.Status.IN_PROGRESS:
        raise Conflict("Inline checks are made on work orders in production.")
    if line.company_id != wo.company_id:
        raise ValidationError({"line": "That line belongs to another company."})
    defects = [(dt, int(c)) for dt, c in defects if int(c) > 0]
    _check_defect_types(wo.company, [dt for dt, _ in defects])
    if len({dt.id for dt, _ in defects}) != len(defects):
        raise ValidationError({"defects": "Each defect type once per check."})
    pieces, defective = int(data["pieces_checked"]), int(data["defective_pieces"])
    total = sum(c for _, c in defects)
    if defective > pieces:
        raise ValidationError({"defective_pieces": "More defective pieces than pieces checked."})
    if defective > total:
        raise ValidationError({"defective_pieces": f"{defective} defective pieces but only {total} defects recorded."})
    if total and not defective:
        raise ValidationError({"defective_pieces": "How many pieces had these defects?"})
    dhu = (Decimal(total) * 100 / pieces).quantize(Decimal("0.01"), ROUND_HALF_UP)
    result = classify(float(dhu))
    insp = InlineInspection.objects.create(
        company=wo.company, production_order=wo, line=line, date=data["date"], operation=data.get("operation", ""),
        operator=data.get("operator", ""), pieces_checked=pieces, defective_pieces=defective, total_defects=total,
        dhu=dhu, result=result, action_taken=data.get("action_taken", ""), inspector=user,
    )
    InlineDefect.objects.bulk_create([InlineDefect(inspection=insp, defect_type=dt, count=c) for dt, c in defects])
    if result == R.RED:
        top = max(defects, key=lambda d: d[1])[0] if defects else None
        CorrectiveAction.objects.create(
            company=wo.company, source=CorrectiveAction.Source.INLINE, inline_inspection=insp, production_order=wo,
            problem=f"Red inline check on {line.name} ({wo.style_no}{', ' + insp.operation if insp.operation else ''}): "
                    f"DHU {dhu}%" + (f", mostly {top.name.lower()}" if top else ""),
            action=insp.action_taken, owner=line.name, due_date=insp.date, created_by=user,
        )
    logger.info("inline_check wo=%s line=%s dhu=%s result=%s", wo.pk, line.pk, dhu, result)
    return insp


# ---------------------------------------------------------------- final inspection

def offered_limit(wo):
    return wo_totals(wo)["finished"]


def build_plan(lot_size, aql_major, aql_minor):
    if str(aql_major) not in aql.AQL_CHOICES or str(aql_minor) not in aql.AQL_CHOICES:
        raise ValidationError({"aql_major": f"AQL must be one of {', '.join(aql.AQL_CHOICES)}."})
    try:
        major, minor = aql.plan(lot_size, aql_major), aql.plan(lot_size, aql_minor)
    except ValueError as e:
        raise ValidationError({"lot_size": str(e)}) from None
    return {"code_letter": major["code"], "sample_size": major["sample_size"],
            "accept_major": major["accept"], "accept_minor": minor["accept"]}


def save_final_defects(fi, defects):
    """defects = [(DefectType, severity, count)] — replaces the findings on a draft."""
    defects = [(dt, sev, int(c)) for dt, sev, c in defects if int(c) > 0]
    _check_defect_types(fi.company, [dt for dt, _, _ in defects])
    keys = [(dt.id, sev) for dt, sev, _ in defects]
    if len(set(keys)) != len(keys):
        raise ValidationError({"defects": "Each defect type and severity once."})
    fi.defects.all().delete()
    FinalDefect.objects.bulk_create([FinalDefect(inspection=fi, defect_type=dt, severity=sev, count=c) for dt, sev, c in defects])
    counts = {s: 0 for s in Severity.values}
    for _, sev, c in defects:
        counts[sev] += c
    fi.critical_found, fi.major_found, fi.minor_found = counts["critical"], counts["major"], counts["minor"]
    fi.save(update_fields=["critical_found", "major_found", "minor_found", "updated_at"])


def final_actions(fi, user):
    if fi.status == FinalInspection.Status.DRAFT:
        return ["edit", "submit", "delete"]
    if fi.status == FinalInspection.Status.FAILED and not hasattr(fi, "reinspection"):
        return ["reinspect"]
    return []


@transaction.atomic
def submit_final(fi, user):
    fi = FinalInspection.objects.select_for_update(of=("self",)).select_related("production_order").get(pk=fi.pk)
    if fi.status != FinalInspection.Status.DRAFT:
        raise Conflict("This inspection is already completed.")
    keys = [k for k, _ in FinalInspection.CHECKLIST]
    unanswered = [label for k, label in FinalInspection.CHECKLIST if fi.checklist.get(k) not in (True, False)]
    if unanswered:
        raise ValidationError({"checklist": f"Answer every checklist item: {', '.join(unanswered)}."})
    reasons = []
    if fi.critical_found:
        reasons.append(f"{fi.critical_found} critical defect(s) — none allowed")
    if fi.major_found > fi.accept_major:
        reasons.append(f"{fi.major_found} major defects, accept ≤ {fi.accept_major} (AQL {fi.aql_major})")
    if fi.minor_found > fi.accept_minor:
        reasons.append(f"{fi.minor_found} minor defects, accept ≤ {fi.accept_minor} (AQL {fi.aql_minor})")
    labels = dict(FinalInspection.CHECKLIST)
    reasons += [f"Checklist: {labels[k]} — not OK" for k in keys if fi.checklist.get(k) is False]
    fi.status = FinalInspection.Status.FAILED if reasons else FinalInspection.Status.PASSED
    fi.fail_reasons, fi.completed_at, fi.inspector = reasons, timezone.now(), fi.inspector or user
    fi.save(update_fields=["status", "fail_reasons", "completed_at", "inspector", "updated_at"])
    if reasons:
        CorrectiveAction.objects.create(
            company=fi.company, source=CorrectiveAction.Source.FINAL, final_inspection=fi, production_order=fi.production_order,
            problem=f"{fi.fi_no} failed for {fi.production_order.style_no} ({fi.lot_size} pcs): " + "; ".join(reasons),
            owner="Production / QA", created_by=user,
        )
    logger.info("final_inspection %s %s", fi.pk, fi.status)
    return fi


@transaction.atomic
def reinspect(fi, user):
    fi = FinalInspection.objects.select_for_update().get(pk=fi.pk)
    existing = FinalInspection.objects.filter(previous=fi).first()
    if existing:
        return existing
    if fi.status != FinalInspection.Status.FAILED:
        raise Conflict("Only failed inspections are re-inspected.")
    return FinalInspection.objects.create(
        company=fi.company, production_order=fi.production_order, round=fi.round + 1, previous=fi,
        inspection_date=timezone.localdate(), inspected_by_party=fi.inspected_by_party, lot_size=fi.lot_size,
        aql_major=fi.aql_major, aql_minor=fi.aql_minor, inspector=user,
        **build_plan(fi.lot_size, fi.aql_major, fi.aql_minor),
    )


# ---------------------------------------------------------------- corrective actions

@transaction.atomic
def close_capa(capa, user, root_cause, action):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can close corrective actions.")
    capa = CorrectiveAction.objects.select_for_update().get(pk=capa.pk)
    if capa.status == CorrectiveAction.Status.CLOSED:
        raise Conflict("This corrective action is already closed.")
    root_cause, action = (root_cause or capa.root_cause).strip(), (action or capa.action).strip()
    if not root_cause or not action:
        raise ValidationError({"root_cause": "Write the root cause and the action taken before closing."})
    capa.root_cause, capa.action = root_cause, action
    capa.status, capa.closed_by, capa.closed_at = CorrectiveAction.Status.CLOSED, user, timezone.now()
    capa.save(update_fields=["root_cause", "action", "status", "closed_by", "closed_at", "updated_at"])
    return capa


# ---------------------------------------------------------------- defect control

def _pct(a, b):
    return round(a / b * 100, 2) if b else None


def summary(date_from, date_to, company=None):
    inline = InlineInspection.objects.filter(date__gte=date_from, date__lte=date_to)
    finals = FinalInspection.objects.filter(inspection_date__gte=date_from, inspection_date__lte=date_to).exclude(status="draft")
    capas = CorrectiveAction.objects.all()
    if company:
        inline, finals, capas = inline.filter(company=company), finals.filter(company=company), capas.filter(company=company)
    agg = inline.aggregate(checks=Count("id"), pieces=Sum("pieces_checked"), defects=Sum("total_defects"), defective=Sum("defective_pieces"))
    pieces, defects = agg["pieces"] or 0, agg["defects"] or 0

    def grouped(field, label):
        rows = inline.values(field, label).annotate(pieces=Sum("pieces_checked"), defects=Sum("total_defects"), checks=Count("id"))
        return sorted(({"id": r[field], "name": r[label], "checks": r["checks"], "pieces": r["pieces"], "defects": r["defects"],
                        "dhu": _pct(r["defects"], r["pieces"])} for r in rows), key=lambda r: -(r["dhu"] or 0))

    pareto = {}
    for r in InlineDefect.objects.filter(inspection__in=inline).values("defect_type", "defect_type__name", "defect_type__category").annotate(n=Sum("count")):
        pareto[r["defect_type"]] = {"defect_type": r["defect_type"], "name": r["defect_type__name"], "category": r["defect_type__category"], "inline": r["n"], "final": 0}
    for r in FinalDefect.objects.filter(inspection__in=finals).values("defect_type", "defect_type__name", "defect_type__category").annotate(n=Sum("count")):
        row = pareto.setdefault(r["defect_type"], {"defect_type": r["defect_type"], "name": r["defect_type__name"], "category": r["defect_type__category"], "inline": 0, "final": 0})
        row["final"] = r["n"]
    rows = sorted(pareto.values(), key=lambda r: -(r["inline"] + r["final"]))
    grand = sum(r["inline"] + r["final"] for r in rows)
    running = 0
    for r in rows:
        r["total"] = r["inline"] + r["final"]
        running += r["total"]
        r["percent"] = _pct(r["total"], grand)
        r["cumulative_percent"] = _pct(running, grand)

    done = finals.count()
    passed = finals.filter(status="passed").count()
    today = timezone.localdate()
    return {
        "from": date_from, "to": date_to,
        "inline": {"checks": agg["checks"], "pieces": pieces, "defects": defects, "defective": agg["defective"] or 0,
                   "dhu": _pct(defects, pieces), "red": inline.filter(result="red").count()},
        "by_line": grouped("line", "line__name"),
        "by_style": grouped("production_order__style_no", "production_order__style_no"),
        "pareto": rows,
        "final": {"inspections": done, "passed": passed, "failed": done - passed, "pass_rate": _pct(passed, done)},
        "capa": {"open": capas.filter(status="open").count(),
                 "overdue": capas.filter(status="open", due_date__lt=today).count()},
    }


DEFAULT_DEFECTS = [
    ("S01", "Broken stitch", "sewing", "major"), ("S02", "Skipped stitch", "sewing", "major"),
    ("S03", "Open seam", "sewing", "critical"), ("S04", "Puckering", "sewing", "minor"),
    ("S05", "Uneven hem", "sewing", "minor"), ("S06", "Twisted seam", "sewing", "major"),
    ("S07", "Wrong stitch density (SPI)", "sewing", "minor"), ("S08", "Raw edge visible", "sewing", "major"),
    ("F01", "Hole", "fabric", "critical"), ("F02", "Shade variation", "fabric", "major"),
    ("F03", "Slub / thick yarn", "fabric", "minor"), ("F04", "Stain / oil spot", "fabric", "major"),
    ("M01", "Measurement out of tolerance", "measurement", "major"),
    ("P01", "Poor pressing / creases", "finishing", "minor"), ("P02", "Untrimmed threads", "finishing", "minor"),
    ("E01", "Print cracking / misprint", "print", "major"),
    ("T01", "Wrong / missing label", "trims", "major"), ("T02", "Broken snap or zip", "trims", "critical"),
    ("K01", "Wrong carton marking", "packing", "minor"), ("K02", "Wrong size ratio in carton", "packing", "major"),
]


def ensure_default_defects(company):
    for code, name, cat, sev in DEFAULT_DEFECTS:
        DefectType.objects.get_or_create(company=company, code=code, defaults={"name": name, "category": cat, "severity": sev})
