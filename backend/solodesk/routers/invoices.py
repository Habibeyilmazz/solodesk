import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select, update

from ..db import today
from ..deps import get_db, get_or_404
from ..models import (
    MAX_LINES,
    AddTimeIn,
    Client,
    Invoice,
    InvoiceCreate,
    InvoiceFields,
    InvoiceLine,
    IssuedCopy,
    LineIn,
    Project,
    Settings,
    StatusIn,
    TimeEntry,
)
from ..money import line_amount, minutes_to_hundredths, totals
from ..pdf import render_invoice

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

# overdue is not stored: it is a sent invoice whose due date has passed
# void is final: its time goes back to unbilled and may be invoiced again elsewhere
TRANSITIONS = {("draft", "sent"), ("sent", "paid"), ("paid", "sent"), ("sent", "void")}


def effective_status(invoice: Invoice, on: dt.date) -> str:
    if invoice.status == "sent" and invoice.due_date < on:
        return "overdue"
    return invoice.status


def invoice_out(invoice: Invoice, client: Client, lines: list[InvoiceLine] | None = None) -> dict:
    out = {
        **invoice.model_dump(),
        "status": effective_status(invoice, today()),
        "client_name": client.name,
    }
    if lines is not None:
        out["lines"] = [line.model_dump() for line in lines]
    return out


def get_lines(db: Session, invoice_id: int) -> list[InvoiceLine]:
    return db.exec(
        select(InvoiceLine)
        .where(InvoiceLine.invoice_id == invoice_id)
        .order_by(InvoiceLine.position, InvoiceLine.id)
    ).all()


def _recalculate(invoice: Invoice, lines: list[InvoiceLine]) -> None:
    for position, line in enumerate(lines):
        line.position = position
        line.amount_minor = line_amount(line.quantity_hundredths, line.unit_price_minor)
    result = totals([line.amount_minor for line in lines], invoice.discount_bp, invoice.tax_rate_bp)
    invoice.sqlmodel_update(result.__dict__)


def _new_line(invoice_id: int, body: LineIn, project_id: int | None = None) -> InvoiceLine:
    return InvoiceLine(
        invoice_id=invoice_id,
        description=body.description,
        quantity_hundredths=body.quantity_hundredths,
        unit_price_minor=body.unit_price_minor,
        amount_minor=0,
        project_id=project_id,
    )


def _span(first: dt.date, last: dt.date) -> str:
    # %-d is not portable, so the day is formatted by hand
    if first == last:
        return f"{first.day} {first:%b %Y}"
    return f"{first.day} {first:%b} to {last.day} {last:%b %Y}"


def _lines_from_time(db: Session, invoice: Invoice, entry_ids: list[int]) -> list[InvoiceLine]:
    """One line per project: total tracked hours at the project's rate. Marks the entries billed."""
    wanted = set(entry_ids)
    rows = db.exec(
        select(TimeEntry, Project)
        .join(Project, TimeEntry.project_id == Project.id)
        .where(TimeEntry.id.in_(wanted))
        .order_by(Project.name, TimeEntry.date)
    ).all()
    if len(rows) != len(wanted):
        raise HTTPException(422, "Some of the selected time entries do not exist.")
    by_project: dict[int, tuple[Project, list[TimeEntry]]] = {}
    for entry, project in rows:
        if project.client_id != invoice.client_id:
            raise HTTPException(422, "Time entries must belong to the invoice's client.")
        if entry.invoice_id is not None or not entry.billable or entry.started_at is not None:
            raise HTTPException(
                422, "Only finished, billable entries that are not on an invoice can be billed."
            )
        by_project.setdefault(project.id, (project, []))[1].append(entry)
        entry.invoice_id = invoice.id
    lines = []
    for project, entries in by_project.values():
        hours = minutes_to_hundredths(sum(e.minutes for e in entries))
        lines.append(
            InvoiceLine(
                invoice_id=invoice.id,
                description=f"{project.name}: {_span(entries[0].date, entries[-1].date)}",
                quantity_hundredths=max(hours, 1),
                unit_price_minor=project.hourly_rate_minor,
                amount_minor=0,
                project_id=project.id,
            )
        )
    return lines


def _release_time(db: Session, invoice_id: int, project_id: int | None = None) -> None:
    """Make an invoice's time entries billable again (all of them, or one project's)."""
    stmt = update(TimeEntry).where(TimeEntry.invoice_id == invoice_id)
    if project_id is not None:
        stmt = stmt.where(TimeEntry.project_id == project_id)
    db.exec(stmt.values(invoice_id=None))


def issued_copy(invoice: Invoice, client: Client, settings: Settings) -> IssuedCopy:
    return IssuedCopy(
        invoice_id=invoice.id, client=client.model_dump_json(), business=settings.model_dump_json()
    )


def parties(db: Session, invoice: Invoice) -> tuple[Client, Settings]:
    """Who the PDF names: the details frozen when the invoice was sent, else today's."""
    copy = db.get(IssuedCopy, invoice.id)
    if copy is None:  # a draft, or an invoice sent before copies were kept
        return db.get(Client, invoice.client_id), db.get(Settings, 1)
    return Client.model_validate_json(copy.client), Settings.model_validate_json(copy.business)


def _draft(db: Session, invoice_id: int) -> Invoice:
    invoice = get_or_404(db, Invoice, invoice_id)
    if invoice.status != "draft":
        raise HTTPException(409, "Only draft invoices can be changed.")
    return invoice


@router.get("")
def list_invoices(
    status: str | None = None, client_id: int | None = None, db: Session = Depends(get_db)
) -> list[dict]:
    query = select(Invoice, Client).join(Client, Invoice.client_id == Client.id)
    if client_id is not None:
        query = query.where(Invoice.client_id == client_id)
    rows = db.exec(query.order_by(Invoice.issue_date.desc(), Invoice.id.desc()))
    out = [invoice_out(invoice, client) for invoice, client in rows]
    return [i for i in out if status is None or i["status"] == status]


@router.post("", status_code=201)
def create_invoice(body: InvoiceCreate, db: Session = Depends(get_db)) -> dict:
    """Create a draft from fixed line items, tracked time (`time_entry_ids`), or both."""
    client = get_or_404(db, Client, body.client_id)
    settings = db.get(Settings, 1)
    issue = body.issue_date or today()
    due = body.due_date or issue + dt.timedelta(days=settings.payment_terms_days)
    if due < issue:
        raise HTTPException(422, "The due date cannot be before the issue date.")
    invoice = Invoice(
        client_id=client.id,
        currency=client.currency,
        issue_date=issue,
        due_date=due,
        tax_rate_bp=settings.default_tax_rate_bp if body.tax_rate_bp is None else body.tax_rate_bp,
        discount_bp=body.discount_bp,
        notes=body.notes,
    )
    db.add(invoice)
    db.flush()
    lines = _lines_from_time(db, invoice, body.time_entry_ids) if body.time_entry_ids else []
    lines += [_new_line(invoice.id, line) for line in body.lines]
    if len(lines) > MAX_LINES:  # time lines count too, or the draft could never be saved again
        raise HTTPException(422, f"An invoice can have at most {MAX_LINES} lines.")
    _recalculate(invoice, lines)
    db.add_all(lines)
    db.commit()
    return invoice_out(invoice, client, get_lines(db, invoice.id))


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    invoice = get_or_404(db, Invoice, invoice_id)
    return invoice_out(invoice, db.get(Client, invoice.client_id), get_lines(db, invoice_id))


@router.put("/{invoice_id}")
def update_invoice(invoice_id: int, body: InvoiceFields, db: Session = Depends(get_db)) -> dict:
    """Replace a draft's fields and lines. Lines sent with an `id` are kept, the rest are new."""
    invoice = _draft(db, invoice_id)
    issue = body.issue_date or invoice.issue_date
    due = body.due_date or invoice.due_date
    if due < issue:
        raise HTTPException(422, "The due date cannot be before the issue date.")
    invoice.issue_date, invoice.due_date = issue, due
    if body.tax_rate_bp is not None:
        invoice.tax_rate_bp = body.tax_rate_bp
    invoice.discount_bp, invoice.notes = body.discount_bp, body.notes

    existing = {line.id: line for line in get_lines(db, invoice_id)}
    kept: list[InvoiceLine] = []
    for item in body.lines:
        if item.id is None:
            line = _new_line(invoice_id, item)
            db.add(line)
        else:
            line = existing.pop(item.id, None)
            if line is None:
                raise HTTPException(422, f"Line {item.id} is not on this invoice.")
            line.sqlmodel_update(item.model_dump(exclude={"id"}))
        kept.append(line)
    for removed in existing.values():
        if removed.project_id is not None:  # a time line: its hours become billable again
            _release_time(db, invoice_id, removed.project_id)
        db.delete(removed)
    _recalculate(invoice, kept)
    db.commit()
    return invoice_out(invoice, db.get(Client, invoice.client_id), get_lines(db, invoice_id))


@router.post("/{invoice_id}/time")
def add_time(invoice_id: int, body: AddTimeIn, db: Session = Depends(get_db)) -> dict:
    """Bill more tracked time on a draft.

    A project that already has a time line on the draft gets the hours added to that line
    (its date span is updated too, unless the description was edited); others get a new line.
    """
    invoice = _draft(db, invoice_id)
    lines = get_lines(db, invoice_id)
    time_lines = {line.project_id: line for line in lines if line.project_id is not None}
    for line in _lines_from_time(db, invoice, body.time_entry_ids):
        old = time_lines.get(line.project_id)
        if old is None:
            lines.append(line)
            db.add(line)
            continue
        dates = db.exec(
            select(TimeEntry.id, TimeEntry.date, TimeEntry.minutes)
            .where(TimeEntry.invoice_id == invoice_id, TimeEntry.project_id == line.project_id)
            .order_by(TimeEntry.date)
        ).all()
        new_ids = set(body.time_entry_ids)
        before = [(d, m) for id_, d, m in dates if id_ not in new_ids]
        # Round the line's total minutes once, as a new draft would; summing two rounded
        # quantities could bill more. A quantity edited by hand only gets the new hours added.
        if old.quantity_hundredths == minutes_to_hundredths(sum(m for _, m in before)):
            old.quantity_hundredths = max(minutes_to_hundredths(sum(m for *_, m in dates)), 1)
        else:
            old.quantity_hundredths += line.quantity_hundredths
        name = db.get(Project, line.project_id).name
        if before and old.description == f"{name}: {_span(before[0][0], before[-1][0])}":
            old.description = f"{name}: {_span(dates[0][1], dates[-1][1])}"
    if len(lines) > MAX_LINES:
        raise HTTPException(422, f"An invoice can have at most {MAX_LINES} lines.")
    _recalculate(invoice, lines)
    db.commit()
    return invoice_out(invoice, db.get(Client, invoice.client_id), get_lines(db, invoice_id))


@router.post("/{invoice_id}/copy", status_code=201)
def copy_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    """A new draft for the same client with this invoice's fixed lines, rates and notes.

    Dated today with the current payment terms. Time lines are left out: their hours are
    already billed, so the new draft takes fresh tracked time through `/time` instead.
    """
    source = get_or_404(db, Invoice, invoice_id)
    terms = db.get(Settings, 1).payment_terms_days
    invoice = Invoice(
        client_id=source.client_id,
        currency=source.currency,  # the copied prices are in this currency
        issue_date=today(),
        due_date=today() + dt.timedelta(days=terms),
        tax_rate_bp=source.tax_rate_bp,
        discount_bp=source.discount_bp,
        notes=source.notes,
    )
    db.add(invoice)
    db.flush()
    lines = [
        InvoiceLine(
            invoice_id=invoice.id,
            description=line.description,
            quantity_hundredths=line.quantity_hundredths,
            unit_price_minor=line.unit_price_minor,
            amount_minor=0,
        )
        for line in get_lines(db, invoice_id)
        if line.project_id is None
    ]
    _recalculate(invoice, lines)
    db.add_all(lines)
    db.commit()
    return invoice_out(invoice, db.get(Client, invoice.client_id), get_lines(db, invoice.id))


@router.post("/{invoice_id}/status")
def set_status(invoice_id: int, body: StatusIn, db: Session = Depends(get_db)) -> dict:
    """draft -> sent (assigns the next number), sent -> paid, paid -> sent (undo), sent -> void.

    A voided invoice keeps its number and lines but is no longer owed, and its tracked time
    becomes billable again. Voiding cannot be undone; a paid invoice must be marked unpaid first.
    """
    invoice = get_or_404(db, Invoice, invoice_id)
    if (invoice.status, body.status) not in TRANSITIONS:
        raise HTTPException(409, f"A {invoice.status} invoice cannot be marked {body.status}.")
    if body.status == "paid" and body.paid_on and body.paid_on > today() + dt.timedelta(days=1):
        # a future month would fall outside the dashboard; one day of slack for time zones
        raise HTTPException(422, "The payment date cannot be in the future.")
    if invoice.status == "draft":
        if not get_lines(db, invoice_id):
            raise HTTPException(409, "Add at least one line before sending.")
        settings = db.get(Settings, 1)
        while True:  # skip numbers already taken, e.g. after the prefix was changed back
            number = f"{settings.invoice_prefix}{settings.next_invoice_number:04d}"
            settings.next_invoice_number += 1
            if not db.exec(select(Invoice.id).where(Invoice.number == number)).first():
                break
        invoice.number = number
        db.add(issued_copy(invoice, db.get(Client, invoice.client_id), settings))
    if body.status == "void":
        _release_time(db, invoice_id)
    invoice.paid_on = (body.paid_on or today()) if body.status == "paid" else None
    invoice.status = body.status
    db.commit()
    return invoice_out(invoice, db.get(Client, invoice.client_id), get_lines(db, invoice_id))


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Drafts only. Sent invoices keep their number, so they stay."""
    invoice = _draft(db, invoice_id)
    _release_time(db, invoice_id)
    for line in get_lines(db, invoice_id):
        db.delete(line)
    db.flush()
    db.delete(invoice)
    db.commit()


@router.get("/{invoice_id}/pdf", response_class=Response)
def invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    invoice = get_or_404(db, Invoice, invoice_id)
    pdf = render_invoice(
        invoice,
        get_lines(db, invoice_id),
        *parties(db, invoice),
        effective_status(invoice, today()),
    )
    name = (invoice.number or f"draft-{invoice.id}").replace("/", "-")
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}.pdf"'},
    )
