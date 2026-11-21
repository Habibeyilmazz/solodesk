import datetime as dt

import pytest

from solodesk.models import Invoice
from solodesk.routers.invoices import effective_status

LINE = {"description": "Brand guidelines", "quantity_hundredths": 100, "unit_price_minor": 250_000}


def make_invoice(api, client_id, **extra):
    response = api.post("/api/invoices", json={"client_id": client_id, "lines": [LINE], **extra})
    assert response.status_code == 201, response.text
    return response.json()


def mark(api, invoice_id, status, **extra):
    return api.post(f"/api/invoices/{invoice_id}/status", json={"status": status, **extra})


def log_time(api, project_id, minutes, date="2026-03-02", **extra):
    body = {"project_id": project_id, "date": date, "minutes": minutes, **extra}
    return api.post("/api/time", json=body).json()


def test_fixed_line_invoice_totals(api, acme):
    invoice = make_invoice(api, acme["client"]["id"], tax_rate_bp=2000, discount_bp=1000)
    assert invoice["status"] == "draft" and invoice["number"] is None
    assert invoice["currency"] == "TRY"
    assert invoice["subtotal_minor"] == 250_000
    assert invoice["discount_minor"] == 25_000
    assert invoice["tax_minor"] == 45_000
    assert invoice["total_minor"] == 270_000
    assert invoice["lines"][0]["amount_minor"] == 250_000


def test_defaults_come_from_settings(api, acme):
    settings = api.get("/api/settings").json()
    api.put("/api/settings", json={**_writable(settings), "default_tax_rate_bp": 1800,
                                   "payment_terms_days": 30})  # fmt: skip
    invoice = make_invoice(api, acme["client"]["id"], issue_date="2026-03-01")
    assert invoice["tax_rate_bp"] == 1800
    assert invoice["due_date"] == "2026-03-31"


def _writable(settings):
    return {k: v for k, v in settings.items() if k != "id"}


def test_invoice_validation(api, acme):
    cid = acme["client"]["id"]
    bad_dates = {"client_id": cid, "issue_date": "2026-03-10", "due_date": "2026-03-01"}
    assert api.post("/api/invoices", json=bad_dates).status_code == 422
    assert (
        api.post("/api/invoices", json={"client_id": cid, "tax_rate_bp": 10_001}).status_code == 422
    )
    negative = {**LINE, "unit_price_minor": -1}
    assert (
        api.post("/api/invoices", json={"client_id": cid, "lines": [negative]}).status_code == 422
    )
    floaty = {**LINE, "unit_price_minor": 10.5}
    assert api.post("/api/invoices", json={"client_id": cid, "lines": [floaty]}).status_code == 422
    assert api.post("/api/invoices", json={"client_id": 999}).status_code == 404


def test_invoice_from_tracked_time_groups_by_project(api, acme):
    cid, pid = acme["client"]["id"], acme["project"]["id"]
    other = api.post(
        "/api/projects", json={"client_id": cid, "name": "App", "hourly_rate_minor": 200_000}
    ).json()
    entries = [
        log_time(api, pid, 90, "2026-03-02"),
        log_time(api, pid, 20, "2026-03-05"),
        log_time(api, other["id"], 60, "2026-03-03"),
    ]
    invoice = api.post(
        "/api/invoices",
        json={"client_id": cid, "time_entry_ids": [e["id"] for e in entries], "tax_rate_bp": 0},
    ).json()
    lines = {line["description"]: line for line in invoice["lines"]}
    assert set(lines) == {"App: 3 Mar 2026", "Website: 2 Mar to 5 Mar 2026"}
    website = lines["Website: 2 Mar to 5 Mar 2026"]
    assert website["quantity_hundredths"] == 183  # 110 min = 1.83 h
    assert website["unit_price_minor"] == 150_000
    assert website["amount_minor"] == 274_500
    assert invoice["total_minor"] == 274_500 + 200_000

    # the entries are now billed: locked, and gone from the unbilled list
    assert api.get("/api/time", params={"unbilled": True}).json() == []
    assert api.delete(f"/api/time/{entries[0]['id']}").status_code == 409
    body = {"project_id": pid, "date": "2026-03-02", "minutes": 1}
    assert api.put(f"/api/time/{entries[0]['id']}", json=body).status_code == 409


def test_time_cannot_be_billed_twice_or_across_clients(api, acme):
    cid, pid = acme["client"]["id"], acme["project"]["id"]
    entry = log_time(api, pid, 60)
    non_billable = log_time(api, pid, 60, billable=False)
    other = api.post("/api/clients", json={"name": "Other"}).json()

    def create(client_id, ids):
        return api.post("/api/invoices", json={"client_id": client_id, "time_entry_ids": ids})

    assert create(other["id"], [entry["id"]]).status_code == 422
    assert create(cid, [non_billable["id"]]).status_code == 422
    assert create(cid, [entry["id"], 999]).status_code == 422
    assert api.get("/api/invoices").json() == []  # failed attempts leave nothing behind
    assert create(cid, [entry["id"]]).status_code == 201
    assert create(cid, [entry["id"]]).status_code == 422


def test_editing_a_draft(api, acme):
    cid, pid = acme["client"]["id"], acme["project"]["id"]
    entry = log_time(api, pid, 60)
    invoice = api.post(
        "/api/invoices",
        json={"client_id": cid, "time_entry_ids": [entry["id"]], "lines": [LINE], "tax_rate_bp": 0},
    ).json()
    time_line, fixed_line = invoice["lines"]
    assert time_line["project_id"] == pid and fixed_line["project_id"] is None

    # keep the fixed line with a new price, drop the time line, add a new line
    updated = api.put(
        f"/api/invoices/{invoice['id']}",
        json={
            "tax_rate_bp": 1000,
            "lines": [
                {"id": fixed_line["id"], **LINE, "unit_price_minor": 100_000},
                {"description": "Hosting", "quantity_hundredths": 300, "unit_price_minor": 5_000},
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert [line["description"] for line in body["lines"]] == ["Brand guidelines", "Hosting"]
    assert body["subtotal_minor"] == 115_000
    assert body["tax_minor"] == 11_500
    assert body["total_minor"] == 126_500
    # dropping the time line released its hours
    assert [e["id"] for e in api.get("/api/time", params={"unbilled": True}).json()] == [
        entry["id"]
    ]

    foreign = {"lines": [{"id": 999, **LINE}]}
    assert api.put(f"/api/invoices/{invoice['id']}", json=foreign).status_code == 422


def test_status_flow_and_sequential_numbers(api, acme):
    cid = acme["client"]["id"]
    first, second, third = (make_invoice(api, cid) for _ in range(3))

    assert mark(api, first["id"], "paid").status_code == 409  # a draft must be sent first
    assert mark(api, second["id"], "sent").json()["number"] == "INV-0001"
    assert mark(api, first["id"], "sent").json()["number"] == "INV-0002"  # numbered when sent
    assert mark(api, first["id"], "sent").status_code == 409

    # sent invoices are frozen
    assert api.put(f"/api/invoices/{first['id']}", json={"lines": [LINE]}).status_code == 409
    assert api.delete(f"/api/invoices/{first['id']}").status_code == 409

    paid = mark(api, first["id"], "paid", paid_on="2026-04-01").json()
    assert (paid["status"], paid["paid_on"]) == ("paid", "2026-04-01")
    undone = mark(api, first["id"], "sent").json()  # undo a mistaken payment
    assert (undone["status"], undone["paid_on"], undone["number"]) == ("sent", None, "INV-0002")

    # deleting a draft leaves no gap in the sequence
    assert api.delete(f"/api/invoices/{third['id']}").status_code == 204
    fourth = make_invoice(api, cid)
    assert mark(api, fourth["id"], "sent").json()["number"] == "INV-0003"


def test_empty_invoice_cannot_be_sent(api, acme):
    invoice = api.post("/api/invoices", json={"client_id": acme["client"]["id"]}).json()
    assert mark(api, invoice["id"], "sent").status_code == 409


def test_number_prefix_and_collisions(api, acme):
    cid = acme["client"]["id"]
    settings = _writable(api.get("/api/settings").json())
    assert mark(api, make_invoice(api, cid)["id"], "sent").json()["number"] == "INV-0001"
    # winding the counter back must not produce a duplicate number
    api.put("/api/settings", json={**settings, "next_invoice_number": 1})
    assert mark(api, make_invoice(api, cid)["id"], "sent").json()["number"] == "INV-0002"
    api.put(
        "/api/settings", json={**settings, "invoice_prefix": "2026/", "next_invoice_number": 41}
    )
    assert mark(api, make_invoice(api, cid)["id"], "sent").json()["number"] == "2026/0041"
    bad = {**settings, "invoice_prefix": "<b>"}
    assert api.put("/api/settings", json=bad).status_code == 422


def test_deleting_a_draft_releases_its_time(api, acme):
    entry = log_time(api, acme["project"]["id"], 45)
    invoice = api.post(
        "/api/invoices", json={"client_id": acme["client"]["id"], "time_entry_ids": [entry["id"]]}
    ).json()
    assert api.delete(f"/api/invoices/{invoice['id']}").status_code == 204
    assert len(api.get("/api/time", params={"unbilled": True}).json()) == 1


@pytest.mark.parametrize(
    ("status", "due", "expected"),
    [
        ("sent", dt.date(2026, 3, 9), "overdue"),
        ("sent", dt.date(2026, 3, 10), "sent"),  # due today is not late yet
        ("draft", dt.date(2026, 3, 1), "draft"),
        ("paid", dt.date(2026, 3, 1), "paid"),
    ],
)
def test_overdue_is_derived_from_due_date(status, due, expected):
    invoice = Invoice(
        client_id=1, currency="TRY", status=status, issue_date=dt.date(2026, 3, 1), due_date=due
    )
    assert effective_status(invoice, dt.date(2026, 3, 10)) == expected


def test_list_filters_by_effective_status(api, acme):
    cid = acme["client"]["id"]
    late = make_invoice(api, cid, issue_date="2020-01-01", due_date="2020-01-15")
    mark(api, late["id"], "sent")
    on_time = make_invoice(api, cid)
    mark(api, on_time["id"], "sent")
    make_invoice(api, cid)

    def ids(status):
        return [i["id"] for i in api.get("/api/invoices", params={"status": status}).json()]

    assert ids("overdue") == [late["id"]]
    assert ids("sent") == [on_time["id"]]
    assert len(ids("draft")) == 1
    assert len(api.get("/api/invoices").json()) == 3


def test_pdf_export(api, acme):
    invoice = make_invoice(api, acme["client"]["id"], notes="Teşekkürler! ₺ ğüşiöç İĞÜŞÖÇ")
    draft = api.get(f"/api/invoices/{invoice['id']}/pdf")
    assert draft.status_code == 200
    assert draft.headers["content-type"] == "application/pdf"
    assert draft.content.startswith(b"%PDF-") and len(draft.content) > 5_000
    assert f"draft-{invoice['id']}.pdf" in draft.headers["content-disposition"]

    mark(api, invoice["id"], "sent")
    sent = api.get(f"/api/invoices/{invoice['id']}/pdf")
    assert "INV-0001.pdf" in sent.headers["content-disposition"]
    assert api.get("/api/invoices/999/pdf").status_code == 404


def test_amounts_are_bounded(api, acme):
    cid = acme["client"]["id"]
    huge_price = {**LINE, "unit_price_minor": 10**9 + 1}
    huge_quantity = {**LINE, "quantity_hundredths": 10**6 + 1}
    for line in (huge_price, huge_quantity):
        assert (
            api.post("/api/invoices", json={"client_id": cid, "lines": [line]}).status_code == 422
        )
    biggest = {**LINE, "unit_price_minor": 10**9, "quantity_hundredths": 10**6}
    invoice = api.post(
        "/api/invoices", json={"client_id": cid, "lines": [biggest] * 200, "tax_rate_bp": 10_000}
    ).json()
    assert invoice["total_minor"] == 4 * 10**15  # exact, and still below 2**53
    assert invoice["total_minor"] < 2**53
