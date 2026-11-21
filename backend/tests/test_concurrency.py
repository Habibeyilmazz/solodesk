"""Requests are serialized, so check-then-write rules hold under concurrent requests."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select

from solodesk.models import Invoice, Settings, TimeEntry

from .test_invoices import make_invoice


def together(count, call):
    """Run `call(i)` from `count` threads released at the same moment."""
    barrier = threading.Barrier(count)

    def run(i):
        barrier.wait()
        return call(i)

    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(run, range(count)))


def test_a_transaction_holds_the_database_until_it_commits(app):
    finished = {}

    def reader():
        with Session(app.state.engine) as other:
            other.exec(select(Settings)).all()
            finished["reader"] = time.monotonic()

    with Session(app.state.engine) as db:
        db.exec(select(Settings)).all()  # the transaction, and the lock, start here
        thread = threading.Thread(target=reader)
        thread.start()
        time.sleep(0.3)
        assert "reader" not in finished  # still waiting for us
        released = time.monotonic()
        db.commit()
    thread.join()
    assert finished["reader"] >= released


def test_only_one_timer_starts(app, api, acme):
    body = {"project_id": acme["project"]["id"]}
    for _ in range(5):
        codes = together(4, lambda _: api.post("/api/timer/start", json=body).status_code)
        assert sorted(codes) == [201, 409, 409, 409]
        api.post("/api/timer/stop")
    with Session(app.state.engine) as db:
        assert not db.exec(select(TimeEntry).where(TimeEntry.started_at.is_not(None))).all()


def test_an_invoice_is_numbered_once(app, api, acme):
    for expected in ("INV-0001", "INV-0002", "INV-0003"):
        invoice = make_invoice(api, acme["client"]["id"])
        url = f"/api/invoices/{invoice['id']}/status"
        codes = together(4, lambda _, url=url: api.post(url, json={"status": "sent"}).status_code)
        assert sorted(codes) == [200, 409, 409, 409]
        assert api.get(f"/api/invoices/{invoice['id']}").json()["number"] == expected
    with Session(app.state.engine) as db:
        assert db.get(Settings, 1).next_invoice_number == 4
        assert len(db.exec(select(Invoice)).all()) == 3


def test_sending_and_deleting_cannot_both_win(api, acme):
    for _ in range(5):
        invoice = make_invoice(api, acme["client"]["id"])
        url = f"/api/invoices/{invoice['id']}"

        def race(i, url=url):
            if i == 0:
                return api.post(f"{url}/status", json={"status": "sent"}).status_code
            return api.delete(url).status_code

        sent, deleted = together(2, race)
        # either it was sent and the delete was refused, or it was deleted first
        assert (sent, deleted) in {(200, 409), (404, 204)}
