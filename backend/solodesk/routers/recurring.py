"""Recurring invoices: a sent invoice copied to a new draft every month, quarter, half or year.

Drafts are made, never sent: you check each one and send it yourself. The app makes due drafts
when it starts, every few minutes while it runs, and when a schedule is created, so drafts
missed while it was stopped are made on the next start, each dated its own scheduled day.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import today
from ..deps import get_db, get_or_404
from ..models import Client, Invoice, Recurring, RecurringIn
from ..money import totals
from .invoices import copy_to_draft, get_lines

router = APIRouter(prefix="/api/recurring", tags=["recurring"])


def add_months(day: dt.date, months: int) -> dt.date:
    """31 Jan + 1 month is 28 (or 29) Feb: the day is clamped to the month's last day."""
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    for d in (day.day, 30, 29, 28):
        try:
            return dt.date(year, month + 1, d)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def next_date(schedule: Recurring) -> dt.date:
    # from the start date each time, so 31 Jan -> 28 Feb -> 31 Mar rather than drifting to 28
    return add_months(schedule.start_date, schedule.made * schedule.every_months)


def make_due(db: Session, on: dt.date) -> int:
    """Create every draft that is due on or before `on`. Returns how many were made."""
    made = 0
    for schedule in db.exec(select(Recurring)).all():
        source = db.get(Invoice, schedule.source_invoice_id)
        while (day := next_date(schedule)) <= on:
            copy_to_draft(db, source, day)
            schedule.made += 1
            made += 1
    db.commit()
    return made


def fixed_amounts(db: Session, invoice: Invoice) -> list[int]:
    """The lines a copy keeps: everything but tracked time."""
    return [line.amount_minor for line in get_lines(db, invoice.id) if line.project_id is None]


def schedule_out(db: Session, schedule: Recurring) -> dict:
    source = db.get(Invoice, schedule.source_invoice_id)
    amounts = fixed_amounts(db, source)
    return {
        **schedule.model_dump(),
        "next_date": next_date(schedule),
        "source_number": source.number,
        "client_name": db.get(Client, source.client_id).name,
        "currency": source.currency,
        # what each draft will total, not the source: its time lines are not copied
        "total_minor": totals(amounts, source.discount_bp, source.tax_rate_bp).total_minor,
    }


@router.get("")
def list_recurring(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.exec(select(Recurring).order_by(Recurring.id)).all()
    return sorted((schedule_out(db, r) for r in rows), key=lambda r: r["next_date"])


@router.post("", status_code=201)
def create_recurring(body: RecurringIn, db: Session = Depends(get_db)) -> dict:
    """Repeat an invoice. A start date of today or earlier makes those drafts at once."""
    source = get_or_404(db, Invoice, body.invoice_id)
    if source.status == "draft":
        # a draft can still change or be deleted; a sent invoice is a fixed template
        raise HTTPException(409, "Send the invoice before repeating it.")
    if not fixed_amounts(db, source):
        raise HTTPException(
            409, "This invoice has only tracked time, which is not repeated. Add fixed lines."
        )
    if body.start_date < today() - dt.timedelta(days=366):
        raise HTTPException(422, "The first draft can be at most a year in the past.")
    schedule = Recurring(
        source_invoice_id=source.id, every_months=body.every_months, start_date=body.start_date
    )
    db.add(schedule)
    db.flush()
    make_due(db, today())
    return schedule_out(db, schedule)


@router.delete("/{recurring_id}", status_code=204)
def stop_recurring(recurring_id: int, db: Session = Depends(get_db)):
    """Stop making drafts. Drafts already made stay."""
    db.delete(get_or_404(db, Recurring, recurring_id))
    db.commit()
