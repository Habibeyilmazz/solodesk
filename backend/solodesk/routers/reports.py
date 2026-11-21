import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, func, select

from ..db import today
from ..deps import get_db
from ..models import Client, Invoice, Project, TimeEntry
from ..money import CURRENCIES, decimal_str, minutes_to_hundredths
from .invoices import effective_status

router = APIRouter(prefix="/api", tags=["reports"])
MONTHS = 12
TOP_CLIENTS = 5
OPEN_SHOWN = 5


def last_months(on: dt.date, count: int = MONTHS) -> list[str]:
    """The `count` months ending with the current one, oldest first, as 'YYYY-MM'."""
    index = on.year * 12 + on.month - 1
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(index - count + 1, index + 1)]


def build_dashboard(db: Session, on: dt.date) -> dict:
    months = last_months(on)
    rows = db.exec(select(Invoice, Client.name).join(Client, Invoice.client_id == Client.id)).all()
    by_currency: dict[str, dict] = {}
    for invoice, client_name in rows:
        if invoice.status == "draft":
            continue
        bucket = by_currency.setdefault(
            invoice.currency,
            {
                "revenue": dict.fromkeys(months, 0),
                "unpaid_minor": 0,
                "unpaid_count": 0,
                "overdue_minor": 0,
                "overdue_count": 0,
                "open": [],
                "clients": {},
            },
        )
        if invoice.status == "paid":
            # revenue is what was earned: net of discount, before tax
            net = invoice.subtotal_minor - invoice.discount_minor
            month = f"{invoice.paid_on:%Y-%m}"
            if month in bucket["revenue"]:
                bucket["revenue"][month] += net
                entry = bucket["clients"].setdefault(
                    invoice.client_id,
                    {"client_id": invoice.client_id, "name": client_name, "net_minor": 0},
                )
                entry["net_minor"] += net
        else:
            bucket["unpaid_minor"] += invoice.total_minor
            bucket["unpaid_count"] += 1
            bucket["open"].append(
                {
                    "id": invoice.id,
                    "number": invoice.number,
                    "client_name": client_name,
                    "due_date": invoice.due_date,
                    "total_minor": invoice.total_minor,
                    "overdue": invoice.due_date < on,
                }
            )
            if effective_status(invoice, on) == "overdue":
                bucket["overdue_minor"] += invoice.total_minor
                bucket["overdue_count"] += 1

    monday = on - dt.timedelta(days=on.weekday())
    per_day = dict(
        db.exec(
            select(TimeEntry.date, func.sum(TimeEntry.minutes))
            .where(TimeEntry.date >= monday, TimeEntry.date < monday + dt.timedelta(days=7))
            .group_by(TimeEntry.date)
        ).all()
    )
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    unbilled = db.exec(
        select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(
            TimeEntry.billable, TimeEntry.invoice_id.is_(None)
        )
    ).one()
    return {
        "currencies": [c for c in CURRENCIES if c in by_currency],
        "by_currency": {
            currency: {
                "revenue_by_month": [
                    {"month": m, "net_minor": v} for m, v in bucket["revenue"].items()
                ],
                "revenue_minor": sum(bucket["revenue"].values()),
                "unpaid_minor": bucket["unpaid_minor"],
                "unpaid_count": bucket["unpaid_count"],
                "overdue_minor": bucket["overdue_minor"],
                "overdue_count": bucket["overdue_count"],
                # the ones to chase first
                "open_invoices": sorted(bucket["open"], key=lambda i: i["due_date"])[:OPEN_SHOWN],
                "top_clients": sorted(
                    bucket["clients"].values(), key=lambda c: c["net_minor"], reverse=True
                )[:TOP_CLIENTS],
            }
            for currency, bucket in by_currency.items()
        },
        "week": {
            "total_minutes": sum(per_day.values()),
            "days": [{"date": d.isoformat(), "minutes": per_day.get(d, 0)} for d in days],
        },
        "unbilled_minutes": unbilled,
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    """Revenue per month (last 12, net of tax), unpaid totals, this week's hours, top clients.

    Money is reported per currency; solodesk does not convert between currencies.
    """
    return build_dashboard(db, today())


def csv_cell(value) -> str:
    """Stop spreadsheets from running user text as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _csv(filename: str, header: list[str], rows) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        "﻿" + out.getvalue(),  # BOM so Excel reads UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/invoices.csv", response_class=Response)
def export_invoices(db: Session = Depends(get_db)):
    on = today()
    rows = db.exec(
        select(Invoice, Client.name)
        .join(Client, Invoice.client_id == Client.id)
        .order_by(Invoice.issue_date, Invoice.id)
    )
    return _csv(
        "solodesk-invoices.csv",
        ["number", "status", "client", "currency", "issue_date", "due_date", "paid_on",
         "subtotal", "discount", "tax", "total"],
        (
            [
                csv_cell(i.number or ""), effective_status(i, on), csv_cell(name), i.currency,
                i.issue_date, i.due_date, i.paid_on or "",
                decimal_str(i.subtotal_minor), decimal_str(i.discount_minor),
                decimal_str(i.tax_minor), decimal_str(i.total_minor),
            ]
            for i, name in rows
        ),
    )  # fmt: skip


@router.get("/export/time.csv", response_class=Response)
def export_time(
    date_from: dt.date | None = None, date_to: dt.date | None = None, db: Session = Depends(get_db)
):
    query = (
        select(TimeEntry, Project.name, Client.name, Invoice.number)
        .join(Project, TimeEntry.project_id == Project.id)
        .join(Client, Project.client_id == Client.id)
        .join(Invoice, TimeEntry.invoice_id == Invoice.id, isouter=True)
        .where(TimeEntry.started_at.is_(None))
        .order_by(TimeEntry.date, TimeEntry.id)
    )
    if date_from:
        query = query.where(TimeEntry.date >= date_from)
    if date_to:
        query = query.where(TimeEntry.date <= date_to)
    return _csv(
        "solodesk-time.csv",
        ["date", "client", "project", "description", "minutes", "hours", "billable", "invoice"],
        (
            [
                e.date, csv_cell(client), csv_cell(project), csv_cell(e.description), e.minutes,
                decimal_str(minutes_to_hundredths(e.minutes)), "yes" if e.billable else "no",
                csv_cell(number or ""),
            ]
            for e, project, client, number in db.exec(query)
        ),
    )  # fmt: skip
