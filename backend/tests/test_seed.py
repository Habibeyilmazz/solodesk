import datetime as dt

from sqlmodel import Session, select

from solodesk.db import make_engine
from solodesk.models import Invoice, InvoiceLine, IssuedCopy, TimeEntry
from solodesk.money import totals
from solodesk.routers.reports import build_dashboard
from solodesk.seed import seed


def test_seed_produces_consistent_books(tmp_path):
    on = dt.date(2026, 11, 21)
    with Session(make_engine(tmp_path / "seed.db")) as db:
        seed(db, on)
        invoices = db.exec(select(Invoice)).all()
        numbers = sorted(i.number for i in invoices if i.number)
        assert numbers == [f"INV-{n:04d}" for n in range(1, len(numbers) + 1)]  # no gaps
        assert {i.status for i in invoices} == {"draft", "sent", "paid"}
        assert len(db.exec(select(IssuedCopy)).all()) == len(numbers)  # every issued invoice
        assert {i.currency for i in invoices} == {"TRY", "USD", "EUR", "GBP"}
        for invoice in invoices:
            amounts = db.exec(
                select(InvoiceLine.amount_minor).where(InvoiceLine.invoice_id == invoice.id)
            ).all()
            assert totals(amounts, invoice.discount_bp, invoice.tax_rate_bp).total_minor == (
                invoice.total_minor
            )
        assert not db.exec(select(TimeEntry).where(TimeEntry.started_at.is_not(None))).first()

        data = build_dashboard(db, on)
        assert data["by_currency"]["USD"]["overdue_count"] == 1
        assert data["by_currency"]["TRY"]["unpaid_count"] == 2
        assert data["week"]["total_minutes"] > 0
        assert len(data["by_currency"]["TRY"]["top_clients"]) == 3
