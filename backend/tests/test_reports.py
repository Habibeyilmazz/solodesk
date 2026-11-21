import csv
import datetime as dt
import io

from sqlmodel import Session

from solodesk.routers.reports import build_dashboard, csv_cell, last_months

from .test_invoices import log_time, make_invoice, mark


def test_last_months_crosses_year_boundary():
    assert last_months(dt.date(2026, 2, 14), 4) == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert len(last_months(dt.date(2026, 11, 21))) == 12


def test_dashboard(app, api, acme):
    cid, pid = acme["client"]["id"], acme["project"]["id"]
    usd = api.post("/api/clients", json={"name": "Northwind", "currency": "USD"}).json()

    paid = make_invoice(api, cid, tax_rate_bp=2000, discount_bp=1000, issue_date="2026-02-20")
    mark(api, paid["id"], "sent")
    mark(api, paid["id"], "paid", paid_on="2026-03-05")
    late = make_invoice(api, cid, tax_rate_bp=2000, issue_date="2026-02-01", due_date="2026-02-10")
    mark(api, late["id"], "sent")
    pending = make_invoice(api, usd["id"], tax_rate_bp=0, issue_date="2026-03-09")
    mark(api, pending["id"], "sent")
    make_invoice(api, cid)  # a draft counts for nothing

    log_time(api, pid, 120, "2026-03-09")  # Monday of that week
    log_time(api, pid, 30, "2026-03-11", billable=False)
    log_time(api, pid, 45, "2026-03-01")  # the week before

    with Session(app.state.engine) as db:
        data = build_dashboard(db, dt.date(2026, 3, 11))

    assert data["currencies"] == ["TRY", "USD"]
    lira = data["by_currency"]["TRY"]
    by_month = {m["month"]: m["net_minor"] for m in lira["revenue_by_month"]}
    assert len(by_month) == 12 and list(by_month)[-1] == "2026-03"
    assert by_month["2026-03"] == 225_000  # 2,500 less 10% discount, tax excluded
    assert lira["revenue_minor"] == 225_000
    assert (lira["unpaid_minor"], lira["unpaid_count"]) == (300_000, 1)  # tax included
    assert (lira["overdue_minor"], lira["overdue_count"]) == (300_000, 1)
    [chase] = lira["open_invoices"]
    assert (chase["number"], chase["overdue"], chase["total_minor"]) == ("INV-0002", True, 300_000)
    assert lira["top_clients"] == [{"client_id": cid, "name": "Acme Yazılım", "net_minor": 225_000}]

    dollars = data["by_currency"]["USD"]
    assert (dollars["unpaid_minor"], dollars["overdue_minor"]) == (250_000, 0)
    assert dollars["open_invoices"][0]["overdue"] is False
    assert dollars["top_clients"] == []

    assert data["week"]["total_minutes"] == 150
    assert [d["minutes"] for d in data["week"]["days"]] == [120, 0, 30, 0, 0, 0, 0]
    assert data["week"]["days"][0]["date"] == "2026-03-09"
    assert data["unbilled_minutes"] == 165  # billable and not invoiced, any week

    assert api.get("/api/dashboard").status_code == 200


def test_dashboard_when_empty(api):
    data = api.get("/api/dashboard").json()
    assert data["currencies"] == [] and data["week"]["total_minutes"] == 0


def rows(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))


def test_invoice_csv(api, acme):
    invoice = make_invoice(api, acme["client"]["id"], tax_rate_bp=2000, issue_date="2026-03-01")
    mark(api, invoice["id"], "sent")
    mark(api, invoice["id"], "paid", paid_on="2026-03-08")
    [row] = rows(api.get("/api/export/invoices.csv"))
    assert row == {
        "number": "INV-0001", "status": "paid", "client": "Acme Yazılım", "currency": "TRY",
        "issue_date": "2026-03-01", "due_date": "2026-03-15", "paid_on": "2026-03-08",
        "subtotal": "2500.00", "discount": "0.00", "tax": "500.00", "total": "3000.00",
    }  # fmt: skip


def test_time_csv_and_formula_escaping(api, acme):
    log_time(api, acme["project"]["id"], 50, "2026-03-02", description="=HYPERLINK(evil)")
    log_time(api, acme["project"]["id"], 60, "2026-04-02", billable=False)
    first, second = rows(api.get("/api/export/time.csv"))
    assert first["description"] == "'=HYPERLINK(evil)"
    assert (first["minutes"], first["hours"], first["billable"]) == ("50", "0.83", "yes")
    assert second["billable"] == "no"
    assert len(rows(api.get("/api/export/time.csv", params={"date_from": "2026-04-01"}))) == 1


def test_csv_cell():
    assert csv_cell("plain") == "plain"
    assert csv_cell("-1+1") == "'-1+1"
    assert csv_cell("@cmd") == "'@cmd"
    assert csv_cell(None) == ""
