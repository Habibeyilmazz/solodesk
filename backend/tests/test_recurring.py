import datetime as dt

from fastapi.testclient import TestClient
from sqlmodel import Session

from solodesk.routers.recurring import add_months, make_due

from .conftest import make_app
from .test_invoices import log_time, make_invoice, mark

TODAY = dt.date.today()


def sent_invoice(api, acme, **extra):
    invoice = make_invoice(api, acme["client"]["id"], **extra)
    assert mark(api, invoice["id"], "sent").status_code == 200
    return invoice


def drafts(api):
    return [i for i in api.get("/api/invoices").json() if i["status"] == "draft"]


def test_add_months_clamps_to_the_month_end():
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert add_months(dt.date(2028, 1, 31), 1) == dt.date(2028, 2, 29)
    assert add_months(dt.date(2026, 1, 31), 3) == dt.date(2026, 4, 30)
    assert add_months(dt.date(2026, 11, 15), 3) == dt.date(2027, 2, 15)
    assert add_months(dt.date(2026, 12, 1), 12) == dt.date(2027, 12, 1)
    assert add_months(dt.date(2026, 5, 9), 0) == dt.date(2026, 5, 9)


def test_a_future_schedule_makes_nothing_until_its_day(api, acme, app):
    source = sent_invoice(api, acme, tax_rate_bp=1800, notes="Retainer")
    start = TODAY + dt.timedelta(days=3)
    r = api.post(
        "/api/recurring",
        json={"invoice_id": source["id"], "every_months": 1, "start_date": start.isoformat()},
    )
    assert r.status_code == 201, r.text
    schedule = r.json()
    assert schedule["next_date"] == start.isoformat()
    assert (schedule["source_number"], schedule["client_name"]) == ("INV-0001", "Acme Yazılım")
    assert schedule["total_minor"] == source["total_minor"]
    assert drafts(api) == []

    with Session(app.state.engine) as db:
        assert make_due(db, start - dt.timedelta(days=1)) == 0
        assert make_due(db, start) == 1
        assert make_due(db, start) == 0  # running again on the same day makes nothing more
    [draft] = drafts(api)
    assert draft["issue_date"] == start.isoformat()
    full = api.get(f"/api/invoices/{draft['id']}").json()
    assert [line["description"] for line in full["lines"]] == ["Brand guidelines"]
    assert (full["tax_rate_bp"], full["notes"], full["total_minor"]) == (
        1800,
        "Retainer",
        source["total_minor"],
    )
    nxt = api.get("/api/recurring").json()[0]["next_date"]
    assert nxt == add_months(start, 1).isoformat()


def test_a_past_start_catches_up_one_draft_per_period(api, acme):
    source = sent_invoice(api, acme)
    start = add_months(TODAY, -2)
    r = api.post(
        "/api/recurring",
        json={"invoice_id": source["id"], "every_months": 1, "start_date": start.isoformat()},
    )
    assert r.status_code == 201, r.text
    dates = sorted(d["issue_date"] for d in drafts(api))
    assert dates == [add_months(start, n).isoformat() for n in range(3)]
    assert r.json()["next_date"] == add_months(start, 3).isoformat()
    terms = api.get("/api/settings").json()["payment_terms_days"]
    for d in drafts(api):
        issued = dt.date.fromisoformat(d["issue_date"])
        assert d["due_date"] == (issued + dt.timedelta(days=terms)).isoformat()


def test_time_lines_are_not_repeated(api, acme):
    entry = log_time(api, acme["project"]["id"], 60)
    source = sent_invoice(api, acme, time_entry_ids=[entry["id"]], tax_rate_bp=2000)
    assert source["total_minor"] == 480_000  # 2,500 fixed + 1,500 for the hour, plus 20%
    r = api.post(
        "/api/recurring",
        json={"invoice_id": source["id"], "every_months": 3, "start_date": TODAY.isoformat()},
    )
    assert r.json()["total_minor"] == 300_000  # what each draft will be: the fixed line only
    [draft] = drafts(api)
    full = api.get(f"/api/invoices/{draft['id']}").json()
    assert [line["project_id"] for line in full["lines"]] == [None]
    assert full["total_minor"] == 300_000


def test_an_invoice_of_only_tracked_time_cannot_repeat(api, acme):
    entry = log_time(api, acme["project"]["id"], 60)
    source = sent_invoice(api, acme, time_entry_ids=[entry["id"]], lines=[])
    body = {"invoice_id": source["id"], "every_months": 1, "start_date": TODAY.isoformat()}
    r = api.post("/api/recurring", json=body)
    assert r.status_code == 409 and "only tracked time" in r.json()["detail"]
    assert drafts(api) == []


def test_validation(api, acme):
    draft = make_invoice(api, acme["client"]["id"])
    body = {"invoice_id": draft["id"], "every_months": 1, "start_date": TODAY.isoformat()}
    assert api.post("/api/recurring", json=body).status_code == 409  # drafts can still change
    mark(api, draft["id"], "sent")
    assert api.post("/api/recurring", json={**body, "every_months": 2}).status_code == 422
    assert api.post("/api/recurring", json={**body, "invoice_id": 999}).status_code == 404
    too_old = (TODAY - dt.timedelta(days=400)).isoformat()
    assert api.post("/api/recurring", json={**body, "start_date": too_old}).status_code == 422
    assert drafts(api) == []


def test_stopping_keeps_the_drafts_already_made(api, acme, app):
    source = sent_invoice(api, acme)
    body = {"invoice_id": source["id"], "every_months": 1, "start_date": TODAY.isoformat()}
    schedule = api.post("/api/recurring", json=body).json()
    assert len(drafts(api)) == 1
    assert api.delete(f"/api/recurring/{schedule['id']}").status_code == 204
    assert api.get("/api/recurring").json() == []
    assert api.delete(f"/api/recurring/{schedule['id']}").status_code == 404
    with Session(app.state.engine) as db:
        assert make_due(db, add_months(TODAY, 5)) == 0
    assert len(drafts(api)) == 1


def test_drafts_missed_while_stopped_are_made_on_start(tmp_path, api, acme, app):
    source = sent_invoice(api, acme)
    start = TODAY + dt.timedelta(days=1)
    body = {"invoice_id": source["id"], "every_months": 1, "start_date": start.isoformat()}
    assert api.post("/api/recurring", json=body).status_code == 201
    # pretend the schedule began yesterday, as if the app had been stopped over its day
    with app.state.engine.begin() as conn:
        conn.exec_driver_sql("UPDATE recurring SET start_date = ?", (TODAY.isoformat(),))
    with TestClient(make_app(app.state.config.db_path)):  # startup runs make_due
        pass
    assert [d["issue_date"] for d in drafts(api)] == [TODAY.isoformat()]


def test_needs_sign_in(anon):
    assert anon.get("/api/recurring").status_code == 401
