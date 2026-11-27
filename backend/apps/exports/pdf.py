"""Commercial invoice and packing list PDFs (ReportLab)."""

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.buyers.models import CreditCheck

from . import services

SMALL_WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
               "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
CURRENCY_WORDS = {"USD": ("US Dollars", "Cents"), "EUR": ("Euros", "Cents"), "GBP": ("Pounds Sterling", "Pence"), "INR": ("Rupees", "Paise")}


def _hundreds(n):
    out = []
    if n >= 100:
        out += [SMALL_WORDS[n // 100], "Hundred"]
        n %= 100
    if n >= 20:
        out.append(TENS[n // 10])
        n %= 10
    if n:
        out.append(SMALL_WORDS[n])
    return out


def words_international(amount, currency):
    """12345.60 USD → 'US Dollars Twelve Thousand Three Hundred Forty Five and Sixty Cents Only'."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    whole, cents = int(amount), int((amount % 1) * 100)
    parts = []
    for value, name in ((10**9, "Billion"), (10**6, "Million"), (1000, "Thousand")):
        if whole >= value:
            parts += _hundreds(whole // value) + [name]
            whole %= value
    parts += _hundreds(whole)
    unit, sub = CURRENCY_WORDS.get(currency, (currency, "Cents"))
    text = f"{unit} {' '.join(parts) or 'Zero'}"
    if cents:
        text += f" and {' '.join(_hundreds(cents))} {sub}"
    return text + " Only"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=15, spaceAfter=4),
        "h": ParagraphStyle("h", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5),
        "n": ParagraphStyle("n", parent=base["Normal"], fontSize=8.5, leading=11),
        "s": ParagraphStyle("s", parent=base["Normal"], fontSize=7.5, leading=9.5, textColor=colors.HexColor("#4b5563")),
    }


def _p(text, style):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _party(title, name, lines, st):
    return [_p(title, st["s"]), _p(name, st["h"]), _p("\n".join(x for x in lines if x), st["n"])]


def _grid(data, widths, header_rows=1, align_right_from=None):
    t = Table(data, colWidths=widths, repeatRows=header_rows)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]
    if align_right_from is not None:
        style.append(("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _header_block(shipment, st):
    order, company, buyer = shipment.order, shipment.company, shipment.order.buyer
    exporter = _party("Exporter", company.name, [company.address, f"{company.city}, {company.country}",
                                                 f"GSTIN / IEC: {company.tax_id}" if company.tax_id else ""], st)
    consignee = _party("Consignee / buyer", buyer.legal_name, [buyer.address, f"{buyer.city}, {buyer.country}",
                                                               f"VAT: {buyer.tax_id}" if buyer.tax_id else ""], st)
    terms = dict(CreditCheck.PaymentTerms.choices).get(order.payment_terms, order.payment_terms)
    info = [
        ["Invoice no.", shipment.invoice_no, "Date", f"{shipment.invoice_date:%d %b %Y}" if shipment.invoice_date else "—"],
        ["Buyer PO", order.buyer_po_no, "Order", order.oc_no],
        ["Terms", f"{order.incoterm} {shipment.port_of_loading}", "Payment", terms],
        ["Port of loading", shipment.port_of_loading, "Port of discharge", shipment.port_of_discharge],
        ["Final destination", shipment.final_destination or buyer.country, "Mode", shipment.get_mode_display()],
        ["Vessel / flight", f"{shipment.vessel} {shipment.voyage}".strip(), "B/L / AWB", shipment.bl_no or "—"],
        ["Container", f"{shipment.container_type} {shipment.container_no}".strip() or "—", "Seal", shipment.seal_no or "—"],
    ]
    parties = Table([[exporter, consignee]], colWidths=[90 * mm, 90 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
                                 ("LINEAFTER", (0, 0), (0, 0), 0.4, colors.HexColor("#9ca3af"))]))
    info_t = Table([[_p(a, st["s"]), _p(b, st["n"]), _p(c, st["s"]), _p(d, st["n"])] for a, b, c, d in info],
                   colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm])
    info_t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [parties, Spacer(1, 3 * mm), info_t, Spacer(1, 4 * mm)]


def render_commercial_invoice(shipment):
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Commercial invoice {shipment.invoice_no}")
    cur = shipment.order.currency
    rows = services.invoice_lines(shipment)
    data = [["#", "Style / description", "HS code", "Cartons", "Pcs", f"Unit price ({cur})", f"Amount ({cur})"]]
    for i, r in enumerate(rows, 1):
        data.append([i, _p(f"{r['style_no']} — {r['description']}", st["n"]), r["hs_code"] or "—", r["cartons"], f"{r['pcs']:,}",
                     f"{r['unit_price']:,.2f}", f"{r['amount']:,.2f}"])
    total = sum((r["amount"] for r in rows), Decimal("0"))
    t = services.shipment_totals(shipment)
    data.append(["", _p("Total", st["h"]), "", t["cartons"], f"{t['pcs']:,}", "", f"{total:,.2f}"])
    story = [_p("COMMERCIAL INVOICE", st["title"])] + _header_block(shipment, st) + [
        _grid(data, [8 * mm, 66 * mm, 20 * mm, 16 * mm, 20 * mm, 24 * mm, 26 * mm], align_right_from=3),
        Spacer(1, 3 * mm),
        _p(f"Amount in words: {words_international(total, cur)}", st["n"]),
        _p(f"Net weight {t['net_weight']:,.2f} kg · Gross weight {t['gross_weight']:,.2f} kg · {t['cbm']:.3f} CBM", st["n"]),
        Spacer(1, 4 * mm),
        _p("We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.", st["s"]),
        Spacer(1, 12 * mm),
        _p(f"For {shipment.company.name}\n\nAuthorised signatory", st["n"]),
    ]
    doc.build(story)
    return buf.getvalue()


def render_packing_list(pl, shipment=None):
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"Packing list {pl.pl_no}")
    groups = list(pl.groups.select_related("production_order"))
    from apps.production.services import ordered_sizes, wo_sizes
    sizes = []
    for g in groups:
        for s in wo_sizes(g.production_order):
            if s not in sizes:
                sizes.append(s)
    sizes = ordered_sizes(sizes, sizes)
    order, buyer = pl.order, pl.order.buyer
    head = Table([[
        _party("Exporter", pl.company.name, [pl.company.address, f"{pl.company.city}, {pl.company.country}"], st),
        _party("Buyer", buyer.legal_name, [f"{buyer.city}, {buyer.country}"], st),
        [_p("Packing list", st["s"]), _p(pl.pl_no, st["h"]),
         _p(f"Date {pl.pack_date:%d %b %Y}\nOrder {order.oc_no} · PO {order.buyer_po_no}\n"
            f"{('Shipment ' + shipment.shipment_no + ' · Invoice ' + shipment.invoice_no) if shipment else ''}", st["n"])],
    ]], colWidths=[90 * mm, 90 * mm, 93 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af"))]))
    hdr = ["Cartons", "Ctns", "Style", "Colour"] + sizes + ["Pcs/ctn", "Total pcs", "NW kg", "GW kg", "L×W×H cm", "CBM"]
    data = [hdr]
    for g in groups:
        data.append([f"{g.from_carton}–{g.to_carton}", g.cartons, g.style_no, g.colourway] + [g.sizes.get(s, "") for s in sizes] + [
            g.pcs_per_carton, f"{g.total_pcs:,}", f"{g.cartons * g.net_weight:,.2f}", f"{g.cartons * g.gross_weight:,.2f}",
            f"{g.length_cm:g}×{g.width_cm:g}×{g.height_cm:g}", f"{g.cartons * g.cbm_per_carton:.3f}"])
    data.append(["Total", pl.total_cartons, "", ""] + [""] * len(sizes) + ["", f"{pl.total_pcs:,}", f"{pl.net_weight:,.2f}",
                                                                          f"{pl.gross_weight:,.2f}", "", f"{pl.cbm:.3f}"])
    fixed = [22, 12, 24, 30] + [14] * len(sizes) + [16, 20, 20, 20, 30, 16]
    scale = 273 / sum(fixed)
    story = [_p("PACKING LIST", st["title"]), head, Spacer(1, 4 * mm),
             _grid(data, [w * scale * mm for w in fixed], align_right_from=4)]
    if pl.shipping_marks:
        story += [Spacer(1, 4 * mm), _p("Shipping marks", st["h"]), _p(pl.shipping_marks, st["n"])]
    doc.build(story)
    return buf.getvalue()
