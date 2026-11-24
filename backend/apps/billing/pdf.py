"""Builds the invoice PDF with ReportLab."""

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_thousand(n):
    words = []
    if n >= 100:
        words += [ONES[n // 100], "Hundred"]
        n %= 100
    if n >= 20:
        words.append(TENS[n // 10])
        n %= 10
    if n:
        words.append(ONES[n])
    return words


def amount_in_words(amount, currency="Rupees", subunit="Paise"):
    """1234567.50 -> 'Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Fifty Paise Only'."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    rupees, paise = int(amount), int((amount % 1) * 100)
    words = []
    for value, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if rupees >= value:
            part = rupees // value
            words += (amount_in_words_int(part) if part >= 1000 else _below_thousand(part)) + [name]
            rupees %= value
    words += _below_thousand(rupees)
    text = f"{currency} {' '.join(words) or 'Zero'}"
    if paise:
        text += f" and {' '.join(_below_thousand(paise))} {subunit}"
    return text + " Only"


def amount_in_words_int(n):
    return amount_in_words(n).replace("Rupees ", "").replace(" Only", "").split()


def indian_number(value):
    """1234567.5 -> '12,34,567.50' (Indian digit grouping)."""
    value = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}{whole}.{frac}"


def render_invoice_pdf(invoice):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Invoice {invoice.invoice_no}", author=invoice.company.name,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=8.5, leading=11, textColor=colors.HexColor("#4b5563"))
    title = ParagraphStyle("title", parent=normal, fontSize=18, leading=22, fontName="Helvetica-Bold")
    right = ParagraphStyle("right", parent=normal, alignment=2)
    company, customer, order = invoice.company, invoice.customer, invoice.sales_order
    currency = company.currency
    line = colors.HexColor("#d1d5db")

    def addr(*parts):
        return "<br/>".join(escape(p).replace("\n", "<br/>") for p in parts if p)

    story = []
    head = Table([[
        [
            Paragraph(escape(company.name), ParagraphStyle("co", parent=normal, fontSize=13, leading=17, fontName="Helvetica-Bold")),
            Paragraph(addr(company.address, " ".join(filter(None, [company.city, company.country])),
                      company.phone, company.email, f"GSTIN: {company.tax_id}" if company.tax_id else ""), small),
        ],
        Paragraph("TAX INVOICE", ParagraphStyle("t", parent=title, alignment=2)),
    ]], colWidths=[110 * mm, 68 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [head, Spacer(1, 8 * mm)]

    meta = Table([[
        Paragraph("<b>Bill to</b><br/>" + addr(customer.name, customer.address,
                  " ".join(filter(None, [customer.city, customer.country])),
                  f"GSTIN: {customer.tax_id}" if customer.tax_id else ""), normal),
        Paragraph(
            f"<b>Invoice no:</b> {invoice.invoice_no}<br/><b>Invoice date:</b> {invoice.invoice_date:%d %b %Y}<br/>"
            f"<b>Due date:</b> {invoice.due_date:%d %b %Y}<br/><b>Order no:</b> {order.order_no}", right),
    ]], colWidths=[100 * mm, 78 * mm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [meta, Spacer(1, 6 * mm)]

    rows = [["#", "Item", "HSN", "Qty", "Rate", "GST %", "GST", "Amount"]]
    for i, item in enumerate(order.items.select_related("product").order_by("id"), start=1):
        rows.append([
            str(i), Paragraph(escape(item.product.name), normal), item.product.hs_code or "-",
            f"{item.quantity.normalize():f}", indian_number(item.unit_price), f"{item.tax_rate.normalize():f}",
            indian_number(item.line_tax), indian_number(item.line_total),
        ])
    items = Table(rows, colWidths=[8 * mm, 58 * mm, 18 * mm, 14 * mm, 22 * mm, 13 * mm, 20 * mm, 25 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, line),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [items, Spacer(1, 4 * mm)]

    totals = [
        ["Subtotal", indian_number(invoice.subtotal)],
        ["GST", indian_number(invoice.tax_amount)],
        [f"Total ({currency})", indian_number(invoice.total)],
        ["Amount paid", indian_number(invoice.amount_paid)],
        [f"Balance due ({currency})", indian_number(invoice.balance)],
    ]
    t = Table(totals, colWidths=[45 * mm, 35 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        ("LINEABOVE", (0, 2), (-1, 2), 0.75, colors.black),
        ("LINEABOVE", (0, 4), (-1, 4), 0.5, line),
    ]))
    story += [t, Spacer(1, 4 * mm)]
    words_currency = "Rupees" if currency == "INR" else currency
    story.append(Paragraph(f"<b>Amount in words:</b> {amount_in_words(invoice.total, words_currency)}", normal))
    if invoice.status == invoice.Status.CANCELLED:
        story += [Spacer(1, 4 * mm), Paragraph("<font color='#dc2626'><b>THIS INVOICE IS CANCELLED</b></font>", normal)]
    if invoice.notes:
        story += [Spacer(1, 4 * mm), Paragraph(f"<b>Notes:</b> {escape(invoice.notes)}", normal)]
    story += [Spacer(1, 14 * mm), Paragraph(f"For <b>{escape(company.name)}</b><br/><br/><br/>Authorised signatory", right),
              Spacer(1, 8 * mm), Paragraph("This is a computer-generated invoice.", small)]
    doc.build(story)
    return buffer.getvalue()
