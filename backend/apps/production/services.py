"""
Production planning and output. Entries change totals that later stages depend on, so the
work order row is locked while an entry is added or removed.
"""

import logging
import math
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.services import Conflict, is_manager

from .models import ActivityLog, ProductionEntry, ProductionLine, ProductionOrder

logger = logging.getLogger(__name__)
ORDER_OVERPLAN_PCT = Decimal("5")  # a style may be planned up to 5% above the order quantity
S = ProductionOrder.Status
E = ProductionEntry.Stage


def log(wo, action, user, note=""):
    ActivityLog.objects.create(production_order=wo, action=action, user=user, note=note)
    logger.info("work_order %s %s user=%s", wo.pk, action, getattr(user, "pk", None))


# ---------------------------------------------------------------- capacity

def add_working_days(start, days):
    """Date after `days` working days counted from start (Sundays off). days=1 → start itself."""
    d, left = start, max(days, 1)
    while True:
        if d.weekday() != 6:
            left -= 1
            if left == 0:
                return d
        d += timedelta(days=1)


def capacity(line, smv, quantity, start):
    target = line.daily_target(smv)
    days = math.ceil(quantity / target) if target else None
    return {"daily_target": target, "working_days": days, "suggested_end": add_working_days(start, days) if days else None}


# ---------------------------------------------------------------- totals

def totals(wo):
    """Output so far (uses prefetched entries when available)."""
    t = {"cut": 0, "cut_rejected": 0, "sewn": 0, "sewing_rejected": 0, "finished": 0, "finishing_rejected": 0}
    cut_sizes = {}
    for e in wo.entries.all():
        if e.stage == E.CUTTING:
            t["cut"] += e.quantity
            t["cut_rejected"] += e.rejected
            for size, q in (e.sizes or {}).items():
                cut_sizes[size] = cut_sizes.get(size, 0) + int(q)
        elif e.stage == E.SEWING:
            t["sewn"] += e.quantity
            t["sewing_rejected"] += e.rejected
        else:
            t["finished"] += e.quantity
            t["finishing_rejected"] += e.rejected
    t["cut_sizes"] = cut_sizes
    t["wip_sewing"] = t["cut"] - t["sewn"] - t["sewing_rejected"]
    t["wip_finishing"] = t["sewn"] - t["finished"] - t["finishing_rejected"]
    t["balance_to_finish"] = max(wo.quantity - t["finished"], 0)
    t["percent_done"] = round(min(t["finished"] / wo.quantity * 100, 100), 1) if wo.quantity else 0
    return t


def cut_limit(wo, size):
    return math.floor(int(wo.sizes.get(size, 0)) * (1 + wo.cut_allowance_pct / 100))


# ---------------------------------------------------------------- planning

def planned_for_line(order_line, exclude=None):
    qs = ProductionOrder.objects.filter(order_line=order_line).exclude(status=S.CANCELLED)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.aggregate(t=Sum("quantity"))["t"] or 0


def plan_warnings(wo):
    warnings = []
    ship = wo.order.ship_date
    if ship and wo.planned_end > ship:
        warnings.append(f"Ends {wo.planned_end:%d %b} — after the shipment date {ship:%d %b %Y}.")
    if ship and wo.planned_end > ship - timedelta(days=7) and wo.planned_end <= ship:
        warnings.append("Less than a week between finishing and shipment (leave time for final inspection and packing).")
    clash = ProductionOrder.objects.filter(
        line=wo.line, planned_start__lte=wo.planned_end, planned_end__gte=wo.planned_start, status__in=[S.PLANNED, S.IN_PROGRESS],
    ).exclude(pk=wo.pk)
    for other in clash:
        warnings.append(f"{wo.line.name} is also booked for {other.wo_no} ({other.style_no}) {other.planned_start:%d %b}–{other.planned_end:%d %b}.")
    cap = capacity(wo.line, wo.smv, wo.quantity, wo.planned_start)
    if wo.status == S.PLANNED and cap["suggested_end"] and cap["suggested_end"] > wo.planned_end:
        warnings.append(f"At {cap['daily_target']} pcs/day the line needs until {cap['suggested_end']:%d %b} ({cap['working_days']} working days).")
    today = timezone.localdate()
    if wo.status == S.IN_PROGRESS:
        t = totals(wo)
        left = wo.quantity - t["finished"]
        sew_days = sorted({e.date for e in wo.entries.all() if e.stage == E.SEWING})
        rate = (t["sewn"] / len(sew_days)) if sew_days else 0
        if wo.planned_end < today and left > 0:
            warnings.append(f"Behind plan: should have finished on {wo.planned_end:%d %b}; {left} pcs still to finish.")
        if rate and left > 0:
            projected = add_working_days(today, math.ceil(max(wo.quantity - t["sewn"], 0) / rate) + 1)
            if ship and projected > ship:
                warnings.append(f"At the current {round(rate)} pcs/day sewing finishes around {projected:%d %b} — after shipment.")
    if wo.tech_pack and not wo.tech_pack.production_approved:
        warnings.append(f"{wo.style_no}: PP sample not approved yet.")
    return warnings


def order_lines_for_planning(order):
    from apps.development.models import TechPack
    rows = []
    for line in order.lines.all():
        tp = (TechPack.objects.filter(buyer=order.buyer, style_no=line.style_no, status=TechPack.Status.RELEASED)
              .order_by("-revision").first())
        rows.append({
            "order_line": line.id, "style_no": line.style_no, "description": line.description, "quantity": line.quantity,
            "planned": planned_for_line(line), "tech_pack": tp.id if tp else None, "sizes": tp.sizes if tp else [],
            "colourways": tp.colourways if tp else [], "production_approved": bool(tp and tp.production_approved),
        })
    return rows


def material_status(wo):
    """Materials for the order: required vs issued to production (from the stores)."""
    from apps.procurement.models import MaterialRequirement
    from apps.stores.services import allocation_plan
    mr = MaterialRequirement.objects.filter(order=wo.order).first()
    if mr is None:
        return {"requirement": None, "lines": []}
    return {"requirement": mr.id, "mr_no": mr.mr_no, "lines": [
        {k: row[k] for k in ("description", "unit", "required_qty", "allocated_qty", "issued_qty")} for row in allocation_plan(mr)
    ]}


# ---------------------------------------------------------------- actions

def wo_actions(wo, user):
    actions = []
    if wo.status == S.PLANNED:
        actions += ["edit", "cancel", "record"]
    elif wo.status == S.IN_PROGRESS:
        actions.append("record")
        if is_manager(user):
            actions.append("complete")
    return actions


def _lock(wo):
    return ProductionOrder.objects.select_for_update().select_related("line", "order").get(pk=wo.pk)


@transaction.atomic
def add_entry(wo, user, data):
    """data: stage, date, sizes (cutting), quantity, rejected, line, lay_no, fabric_used, remarks."""
    wo = _lock(wo)
    if wo.status not in (S.PLANNED, S.IN_PROGRESS):
        raise Conflict(f"This work order is {wo.get_status_display().lower()}; no more output can be recorded.")
    stage, date = data["stage"], data["date"]
    if date > timezone.localdate():
        raise ValidationError({"date": "Output can't be recorded for a future date."})
    rejected = int(data.get("rejected") or 0)
    t = totals(wo)
    sizes = {}
    if stage == E.CUTTING:
        sizes = {str(k): int(v) for k, v in (data.get("sizes") or {}).items() if v not in (None, "", 0, "0")}
        if not sizes:
            raise ValidationError({"sizes": "Enter the pieces cut per size."})
        for size, q in sizes.items():
            if size not in wo.sizes:
                raise ValidationError({"sizes": f"Size {size} is not on this work order."})
            if q < 0:
                raise ValidationError({"sizes": "Pieces can't be negative."})
            limit = cut_limit(wo, size)
            if t["cut_sizes"].get(size, 0) + q > limit:
                raise ValidationError({"sizes": f"Size {size}: that makes {t['cut_sizes'].get(size, 0) + q} cut; the plan allows {limit} "
                                                f"({wo.sizes[size]} + {wo.cut_allowance_pct}% allowance)."})
        quantity = sum(sizes.values())
    else:
        quantity = int(data.get("quantity") or 0)
        if quantity <= 0 and rejected <= 0:
            raise ValidationError({"quantity": "Enter the good pieces (or rejects)."})
        if stage == E.SEWING:
            available = t["wip_sewing"]
            if quantity + rejected > available:
                raise ValidationError({"quantity": f"Only {available} cut pieces are waiting for sewing."})
        else:
            available = t["wip_finishing"]
            if quantity + rejected > available:
                raise ValidationError({"quantity": f"Only {available} sewn pieces are waiting for finishing."})
    line = data.get("line") or (wo.line if stage == E.SEWING else None)
    if line and line.company_id != wo.company_id:
        raise ValidationError({"line": "That line belongs to another company."})
    entry = ProductionEntry.objects.create(
        production_order=wo, stage=stage, date=date, sizes=sizes, quantity=quantity, rejected=rejected, line=line,
        lay_no=data.get("lay_no", ""), fabric_used=data.get("fabric_used"), remarks=data.get("remarks", ""), entered_by=user,
    )
    if wo.status == S.PLANNED:
        wo.status, wo.started_at = S.IN_PROGRESS, timezone.now()
        wo.save(update_fields=["status", "started_at", "updated_at"])
        log(wo, "started", user, f"First {stage} entry")
    note = f"{entry.get_stage_display()} {date:%d %b}: {quantity} pcs" + (f", {rejected} rejected" if rejected else "")
    log(wo, f"{stage}_recorded", user, note)
    if stage == E.FINISHING and t["finished"] + quantity >= wo.quantity:
        wo.status, wo.completed_at = S.COMPLETED, timezone.now()
        wo.save(update_fields=["status", "completed_at", "updated_at"])
        log(wo, "completed", user, f"{t['finished'] + quantity} pcs finished")
    return entry


@transaction.atomic
def delete_entry(entry, user):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can delete production entries.")
    wo = _lock(entry.production_order)
    if wo.status not in (S.PLANNED, S.IN_PROGRESS):
        raise Conflict("Entries of a closed work order can't be deleted.")
    t = totals(wo)
    if entry.stage == E.CUTTING and t["cut"] - entry.quantity < t["sewn"] + t["sewing_rejected"]:
        raise Conflict("Sewing already used these cut pieces; delete the sewing entries first.")
    if entry.stage == E.SEWING and t["sewn"] - entry.quantity < t["finished"] + t["finishing_rejected"]:
        raise Conflict("Finishing already used these sewn pieces; delete the finishing entries first.")
    note = f"Deleted {entry.get_stage_display().lower()} entry of {entry.date:%d %b}: {entry.quantity} pcs"
    entry.delete()
    if not wo.entries.exists():
        wo.status, wo.started_at = S.PLANNED, None
        wo.save(update_fields=["status", "started_at", "updated_at"])
    log(wo, "entry_deleted", user, note)
    return wo


@transaction.atomic
def complete_wo(wo, user, reason=""):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can close a work order.")
    wo = _lock(wo)
    if wo.status != S.IN_PROGRESS:
        raise Conflict("Only work orders in production can be closed.")
    t = totals(wo)
    if t["finished"] < wo.quantity and not reason:
        raise ValidationError({"reason": f"Only {t['finished']} of {wo.quantity} pcs are finished; give the reason for closing short."})
    wo.status, wo.completed_at, wo.close_reason = S.COMPLETED, timezone.now(), reason
    wo.save(update_fields=["status", "completed_at", "close_reason", "updated_at"])
    log(wo, "completed", user, reason or "Closed")
    return wo


@transaction.atomic
def cancel_wo(wo, user, reason=""):
    wo = _lock(wo)
    if wo.status != S.PLANNED:
        raise Conflict("Only work orders that haven't started can be cancelled.")
    wo.status, wo.close_reason = S.CANCELLED, reason
    wo.save(update_fields=["status", "close_reason", "updated_at"])
    log(wo, "cancelled", user, reason)
    return wo


# ---------------------------------------------------------------- reports

def daily_report(date, company=None):
    lines = ProductionLine.objects.filter(is_active=True)
    if company:
        lines = lines.filter(company=company)
    entries = ProductionEntry.objects.filter(date=date).select_related("production_order", "line")
    rows = []
    for line in lines:
        running = (ProductionOrder.objects.filter(line=line, status__in=[S.PLANNED, S.IN_PROGRESS],
                                                  planned_start__lte=date, planned_end__gte=date).order_by("planned_start").first())
        sewn = [e for e in entries if e.stage == E.SEWING and e.line_id == line.id]
        good, rej = sum(e.quantity for e in sewn), sum(e.rejected for e in sewn)
        smv = running.smv if running else (sewn[0].production_order.smv if sewn else None)
        target = line.daily_target(smv) if smv else 0
        minutes = line.operators * line.working_minutes
        rows.append({
            "line": line.id, "line_name": line.name, "operators": line.operators,
            "work_order": running.id if running else None, "wo_no": running.wo_no if running else None,
            "style_no": running.style_no if running else (sewn[0].production_order.style_no if sewn else None),
            "smv": smv, "target": target, "sewn": good, "rejected": rej,
            "achievement_pct": round(good / target * 100, 1) if target else None,
            "efficiency_pct": round(float(good * smv) / minutes * 100, 1) if smv and minutes else None,
        })
    by_stage = {s: {"good": 0, "rejected": 0} for s in E.values}
    for e in entries:
        if company and e.production_order.company_id != int(company):
            continue
        by_stage[e.stage]["good"] += e.quantity
        by_stage[e.stage]["rejected"] += e.rejected
    return {"date": date, "lines": rows, "stages": by_stage}
