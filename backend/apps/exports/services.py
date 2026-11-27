import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.buyers.services import Conflict, is_manager
from apps.merchandising.models import OrderConfirmation
from apps.production.services import totals as wo_totals
from apps.production.services import wo_sizes
from apps.quality.models import FinalInspection

from .models import ActivityLog, CartonGroup, ExportDocument, ExportShipment, PackingList

logger = logging.getLogger(__name__)
PL, SH = PackingList.Status, ExportShipment.Status
ORDER_OVERSHIP_PCT = Decimal("5")


def log(doc_type, doc, action, user, note=""):
    ActivityLog.objects.create(doc_type=doc_type, doc_id=doc.pk, action=action, user=user, note=note)
    logger.info("%s %s %s user=%s", doc_type, doc.pk, action, getattr(user, "pk", None))


def history(doc_type, doc_id):
    return ActivityLog.objects.filter(doc_type=doc_type, doc_id=doc_id).select_related("user")


# ---------------------------------------------------------------- packing

def packed_qty(wo, exclude_list=None):
    """Pieces of this work order on finalized packing lists."""
    groups = CartonGroup.objects.filter(production_order=wo, packing_list__status=PL.FINALIZED)
    if exclude_list is not None:
        groups = groups.exclude(packing_list=exclude_list)
    return sum(g.total_pcs for g in groups)


def wo_pack_status(wo, exclude_list=None):
    finished = wo_totals(wo)["finished"]
    passed = FinalInspection.objects.filter(production_order=wo, status=FinalInspection.Status.PASSED).aggregate(t=Sum("lot_size"))["t"] or 0
    packed = packed_qty(wo, exclude_list)
    return {"production_order": wo.id, "wo_no": wo.wo_no, "style_no": wo.style_no, "colourway": wo.colourway,
            "sizes": wo_sizes(wo), "finished": finished, "passed_inspection": passed, "packed": packed,
            "packable": max(min(finished, passed) - packed, 0)}


def check_groups(order, groups, packing_list=None):
    """Validate carton groups: work orders of the order, sizes, numbering, packable quantities."""
    if not groups:
        raise ValidationError({"groups": "Add the cartons."})
    ranges = sorted((g["from_carton"], g["to_carton"]) for g in groups)
    for (a1, b1), (a2, _) in zip(ranges, ranges[1:]):
        if a2 <= b1:
            raise ValidationError({"groups": f"Carton numbers overlap around carton {a2}."})
    per_wo = {}
    for g in groups:
        wo = g["production_order"]
        if wo.order_id != order.id:
            raise ValidationError({"groups": f"{wo.wo_no} is for another order."})
        sizes = {str(k): int(v) for k, v in g["sizes"].items() if int(v) > 0}
        if not sizes:
            raise ValidationError({"groups": f"Cartons {g['from_carton']}–{g['to_carton']}: enter pieces per size."})
        unknown = [s for s in sizes if s not in wo.sizes]
        if unknown:
            raise ValidationError({"groups": f"{wo.style_no} has no size {', '.join(unknown)}."})
        g["sizes"] = sizes
        per_wo[wo] = per_wo.get(wo, 0) + (g["to_carton"] - g["from_carton"] + 1) * sum(sizes.values())
    for wo, pcs in per_wo.items():
        status = wo_pack_status(wo, exclude_list=packing_list)
        if pcs > status["packable"]:
            if not status["passed_inspection"]:
                raise ValidationError({"groups": f"{wo.style_no}: no passed final inspection yet — goods can't be packed for shipment."})
            raise ValidationError({"groups": f"{wo.style_no}: {pcs} pcs packed but only {status['packable']} can be "
                                             f"(finished {status['finished']}, passed inspection {status['passed_inspection']}, "
                                             f"already packed {status['packed']})."})
    return groups


def packing_actions(pl, user):
    if pl.status == PL.DRAFT:
        return ["edit", "finalize", "delete"]
    if pl.shipment_id and pl.shipment.status in (SH.SHIPPED, SH.DELIVERED):
        return ["pdf"]
    return ["pdf"] + (["reopen"] if is_manager(user) else [])


@transaction.atomic
def finalize_packing_list(pl, user):
    pl = PackingList.objects.select_for_update().get(pk=pl.pk)
    if pl.status != PL.DRAFT:
        raise Conflict("Only draft packing lists can be finalized.")
    OrderConfirmation.objects.select_for_update().get(pk=pl.order_id)  # one finalize per order at a time
    groups = [{"production_order": g.production_order, "from_carton": g.from_carton, "to_carton": g.to_carton, "sizes": g.sizes}
              for g in pl.groups.select_related("production_order")]
    check_groups(pl.order, groups, packing_list=pl)
    numbers = sorted(n for g in groups for n in (g["from_carton"], g["to_carton"]))
    if numbers[0] != 1:
        raise ValidationError({"groups": "Carton numbering must start at 1."})
    expected = 1
    for g in sorted(groups, key=lambda x: x["from_carton"]):
        if g["from_carton"] != expected:
            raise ValidationError({"groups": f"Carton {expected} is missing — numbering must have no gaps."})
        expected = g["to_carton"] + 1
    pl.status, pl.finalized_by, pl.finalized_at = PL.FINALIZED, user, timezone.now()
    pl.save(update_fields=["status", "finalized_by", "finalized_at", "updated_at"])
    log("packing_list", pl, "finalized", user, f"{pl.total_cartons} cartons, {pl.total_pcs} pcs, {pl.cbm} CBM")
    return pl


@transaction.atomic
def reopen_packing_list(pl, user):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can reopen a packing list.")
    pl = PackingList.objects.select_for_update(of=("self",)).select_related("shipment").get(pk=pl.pk)
    if pl.status != PL.FINALIZED:
        raise Conflict("Only finalized packing lists can be reopened.")
    if pl.shipment_id and pl.shipment.status in (SH.SHIPPED, SH.DELIVERED):
        raise Conflict("This packing list has shipped.")
    pl.status, pl.shipment = PL.DRAFT, None
    pl.save(update_fields=["status", "shipment", "updated_at"])
    log("packing_list", pl, "reopened", user)
    return pl


# ---------------------------------------------------------------- shipments

def create_documents(shipment):
    ExportDocument.objects.bulk_create([ExportDocument(shipment=shipment, doc_type=t) for t, _ in ExportDocument.DocType.choices])
    ExportDocument.objects.filter(shipment=shipment, doc_type=ExportDocument.DocType.COMMERCIAL_INVOICE).update(
        number=shipment.invoice_no, status=ExportDocument.Status.READY)


def attach_packing_lists(shipment, lists, user):
    for pl in lists:
        if pl.order_id != shipment.order_id:
            raise ValidationError({"packing_lists": f"{pl.pl_no} is for another order."})
        if pl.status != PL.FINALIZED:
            raise ValidationError({"packing_lists": f"{pl.pl_no} is not finalized."})
        if pl.shipment_id and pl.shipment_id != shipment.id and pl.shipment.status != SH.CANCELLED:
            raise ValidationError({"packing_lists": f"{pl.pl_no} is already on {pl.shipment.shipment_no}."})
    keep = {pl.id for pl in lists}
    PackingList.objects.filter(shipment=shipment).exclude(id__in=keep).update(shipment=None)
    PackingList.objects.filter(id__in=keep).update(shipment=shipment)
    pl_doc = ExportDocument.objects.filter(shipment=shipment, doc_type=ExportDocument.DocType.PACKING_LIST)
    pl_doc.update(number=", ".join(pl.pl_no for pl in lists), status=ExportDocument.Status.READY if lists else ExportDocument.Status.PENDING)


def shipment_totals(shipment):
    lists = list(shipment.packing_lists.all())
    return {"packing_lists": len(lists), "cartons": sum(p.total_cartons for p in lists), "pcs": sum(p.total_pcs for p in lists),
            "net_weight": sum((p.net_weight for p in lists), Decimal("0")), "gross_weight": sum((p.gross_weight for p in lists), Decimal("0")),
            "cbm": sum((p.cbm for p in lists), Decimal("0"))}


def invoice_lines(shipment):
    """Commercial invoice: packed pieces per style at the order price."""
    prices = {line.style_no: line for line in shipment.order.lines.all()}
    per_style = {}
    for pl in shipment.packing_lists.all():
        for g in pl.groups.all():
            row = per_style.setdefault(g.style_no, {"style_no": g.style_no, "pcs": 0, "cartons": 0})
            row["pcs"] += g.total_pcs
            row["cartons"] += g.cartons
    rows = []
    for style, row in per_style.items():
        line = prices.get(style)
        price = line.unit_price if line else Decimal("0")
        rows.append({**row, "description": line.description if line else style, "hs_code": shipment.hs_codes.get(style, ""),
                     "unit_price": price, "amount": (price * row["pcs"]).quantize(Decimal("0.01"))})
    return rows


def shipment_actions(shipment, user):
    return {
        SH.PLANNED: ["edit", "book", "cancel"],
        SH.BOOKED: ["edit", "ship", "cancel"],
        SH.SHIPPED: ["edit_docs", "deliver"],
        SH.DELIVERED: ["edit_docs"],
        SH.CANCELLED: [],
    }[shipment.status]


def _lock(shipment):
    return ExportShipment.objects.select_for_update(of=("self",)).select_related("order").get(pk=shipment.pk)


@transaction.atomic
def book_shipment(shipment, user):
    s = _lock(shipment)
    if s.status != SH.PLANNED:
        raise Conflict("Only planned shipments can be booked.")
    missing = {}
    if not s.packing_lists.exists():
        missing["packing_lists"] = "Add the finalized packing lists."
    if not s.port_of_discharge:
        missing["port_of_discharge"] = "Enter the port of discharge."
    if not s.etd:
        missing["etd"] = "Enter the ETD."
    if not s.forwarder:
        missing["forwarder"] = "Enter the forwarder."
    if missing:
        raise ValidationError(missing)
    s.status = SH.BOOKED
    s.save(update_fields=["status", "updated_at"])
    log("shipment", s, "booked", user, f"{s.get_mode_display()} with {s.forwarder}, ETD {s.etd:%d %b}")
    return s


@transaction.atomic
def ship(shipment, user, on_board_date=None):
    s = _lock(shipment)
    if s.status != SH.BOOKED:
        raise Conflict("Only booked shipments can be marked shipped.")
    on_board = on_board_date or timezone.localdate()
    missing = {}
    if not s.vessel:
        missing["vessel"] = "Enter the vessel or flight."
    if not s.bl_no:
        missing["bl_no"] = "Enter the B/L or AWB number."
    if not s.shipping_bill_no:
        missing["shipping_bill_no"] = "Enter the shipping bill number."
    if s.mode == ExportShipment.Mode.SEA and not s.container_type:
        missing["container_type"] = "Enter the container type (20GP, 40HC, LCL…)."
    if on_board > timezone.localdate():
        missing["on_board_date"] = "The on-board date can't be in the future."
    if missing:
        raise ValidationError(missing)
    s.status, s.on_board_date = SH.SHIPPED, on_board
    s.invoice_date = s.invoice_date or on_board
    s.save(update_fields=["status", "on_board_date", "invoice_date", "updated_at"])
    docs = ExportDocument.objects.filter(shipment=s)
    docs.filter(doc_type=ExportDocument.DocType.BILL_OF_LADING).update(number=s.bl_no, date=on_board, status=ExportDocument.Status.READY)
    docs.filter(doc_type=ExportDocument.DocType.SHIPPING_BILL).update(number=s.shipping_bill_no, date=s.shipping_bill_date, status=ExportDocument.Status.READY)
    docs.filter(doc_type=ExportDocument.DocType.COMMERCIAL_INVOICE).update(date=s.invoice_date)
    t = shipment_totals(s)
    log("shipment", s, "shipped", user, f"On board {on_board:%d %b} · {s.vessel} · B/L {s.bl_no} · {t['cartons']} cartons, {t['pcs']} pcs")
    return s


@transaction.atomic
def deliver(shipment, user, delivered_date=None):
    s = _lock(shipment)
    if s.status != SH.SHIPPED:
        raise Conflict("Only shipped shipments can be marked delivered.")
    s.status, s.delivered_date = SH.DELIVERED, delivered_date or timezone.localdate()
    s.save(update_fields=["status", "delivered_date", "updated_at"])
    log("shipment", s, "delivered", user, f"Delivered {s.delivered_date:%d %b}")
    return s


@transaction.atomic
def cancel_shipment(shipment, user, reason):
    if not reason:
        raise ValidationError({"reason": "Give a reason for cancelling."})
    s = _lock(shipment)
    if s.status not in (SH.PLANNED, SH.BOOKED):
        raise Conflict("Shipped shipments can't be cancelled.")
    s.status, s.cancel_reason = SH.CANCELLED, reason
    s.save(update_fields=["status", "cancel_reason", "updated_at"])
    PackingList.objects.filter(shipment=s).update(shipment=None)
    log("shipment", s, "cancelled", user, reason)
    return s
