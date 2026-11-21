"""Invoice PDF. DejaVu Sans is bundled so Turkish letters and ₺ render everywhere."""

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from .models import Client, Invoice, InvoiceLine, Settings
from .money import format_money

FONTS = Path(__file__).parent / "fonts"
INK = (27, 42, 74)
MUTED = (92, 103, 128)
RULE = (213, 220, 227)


def _quantity(hundredths: int) -> str:
    return f"{hundredths // 100}.{hundredths % 100:02d}".rstrip("0").rstrip(".")


def _date(d) -> str:
    return f"{d.day} {d:%B %Y}"  # %-d is not portable


def _percent(bp: int) -> str:
    return f"{bp // 100}.{bp % 100:02d}".rstrip("0").rstrip(".") + "%"


def render_invoice(
    invoice: Invoice, lines: list[InvoiceLine], client: Client, settings: Settings, status: str
) -> bytes:
    def money(minor: int) -> str:
        return format_money(minor, invoice.currency)

    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_font("DejaVu", "", FONTS / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", FONTS / "DejaVuSans-Bold.ttf")
    pdf.set_title(f"Invoice {invoice.number or 'draft'}")
    pdf.add_page()
    width = pdf.epw

    def text(value: str, size=9.5, style="", color=INK, w=0, align="L", h=5.2):
        pdf.set_font("DejaVu", style, size)
        pdf.set_text_color(*color)
        pdf.multi_cell(w, h, value, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # header: who is billing, and the invoice number
    top = pdf.get_y()
    text(settings.business_name, size=16, style="B", w=width * 0.6, h=8)
    details = "\n".join(
        part
        for part in (
            settings.business_address,
            settings.business_email,
            f"Tax ID: {settings.tax_id}" if settings.tax_id else "",
        )
        if part
    )
    if details:
        text(details, color=MUTED, w=width * 0.6)
    left_bottom = pdf.get_y()

    pdf.set_xy(pdf.l_margin + width * 0.6, top)
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(*INK)
    pdf.cell(width * 0.4, 8, "Invoice", align="R", new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(*MUTED)
    label = invoice.number or "Draft, not yet numbered"
    for row in (label, f"Issued {_date(invoice.issue_date)}", f"Due {_date(invoice.due_date)}"):
        pdf.cell(width * 0.4, 5.2, row, align="R", new_x=XPos.LEFT, new_y=YPos.NEXT)
    if status == "paid" and invoice.paid_on:
        pdf.set_text_color(31, 122, 77)
        pdf.cell(width * 0.4, 5.2, f"Paid {_date(invoice.paid_on)}", align="R")
        pdf.ln()
    pdf.set_y(max(left_bottom, pdf.get_y()) + 10)

    # bill to
    text("Bill to", size=8.5, color=MUTED)
    text(client.name, style="B", size=11, h=6)
    client_details = "\n".join(
        part
        for part in (
            client.address,
            client.email,
            f"Tax ID: {client.tax_id}" if client.tax_id else "",
        )
        if part
    )
    if client_details:
        text(client_details, color=MUTED)
    pdf.ln(8)

    # lines
    pdf.set_draw_color(*RULE)
    pdf.set_text_color(*INK)
    pdf.set_font("DejaVu", "", 9.5)
    with pdf.table(
        col_widths=(52, 12, 18, 18),
        text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT"),
        borders_layout="HORIZONTAL_LINES",
        line_height=6,
        padding=(2, 1.5),
        headings_style=FontFace(emphasis="BOLD", color=INK),
    ) as table:
        table.row(("Description", "Qty", "Unit price", "Amount"))
        for line in lines:
            table.row(
                (
                    # one paragraph: a table row taller than a page cannot be drawn at all
                    " ".join(line.description.split()),
                    _quantity(line.quantity_hundredths),
                    money(line.unit_price_minor),
                    money(line.amount_minor),
                )
            )
    pdf.ln(5)

    # totals, right-aligned under the amount column
    def total_row(name: str, value: str, bold=False):
        pdf.set_font("DejaVu", "B" if bold else "", 11 if bold else 9.5)
        pdf.set_text_color(*(INK if bold else MUTED))
        pdf.set_x(pdf.l_margin + width * 0.5)
        pdf.cell(width * 0.25, 7 if bold else 6, name)
        pdf.set_text_color(*INK)
        pdf.cell(
            width * 0.25, 7 if bold else 6, value, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )

    total_row("Subtotal", money(invoice.subtotal_minor))
    if invoice.discount_minor:
        total_row(
            f"Discount ({_percent(invoice.discount_bp)})", "-" + money(invoice.discount_minor)
        )
    if invoice.tax_rate_bp:
        total_row(f"Tax ({_percent(invoice.tax_rate_bp)})", money(invoice.tax_minor))
    y = pdf.get_y() + 1
    pdf.line(pdf.l_margin + width * 0.5, y, pdf.l_margin + width, y)
    pdf.ln(2)
    total_row(f"Total ({invoice.currency})", money(invoice.total_minor), bold=True)

    for block in (invoice.notes, settings.invoice_footer):
        if block:
            pdf.ln(8)
            text(block, color=MUTED)

    return bytes(pdf.output())
