import datetime as dt

TODAY = dt.date.today().isoformat()


def test_client_crud_and_validation(api):
    assert api.post("/api/clients", json={"name": "   "}).status_code == 422
    assert api.post("/api/clients", json={"name": "X", "currency": "JPY"}).status_code == 422
    assert api.post("/api/clients", json={"name": "X", "surprise": 1}).status_code == 422

    created = api.post("/api/clients", json={"name": "  Çınar Öztürk  ", "currency": "EUR"})
    assert created.status_code == 201
    client = created.json()
    assert client["name"] == "Çınar Öztürk" and client["currency"] == "EUR"

    updated = api.put(f"/api/clients/{client['id']}", json={"name": "Çınar Ltd", "currency": "GBP"})
    assert updated.json()["currency"] == "GBP"
    assert [c["name"] for c in api.get("/api/clients").json()] == ["Çınar Ltd"]

    assert api.delete(f"/api/clients/{client['id']}").status_code == 204
    assert api.get("/api/clients").json() == []
    assert api.put("/api/clients/999", json={"name": "Ghost"}).status_code == 404


def test_client_with_projects_cannot_be_deleted(api, acme):
    assert api.delete(f"/api/clients/{acme['client']['id']}").status_code == 409


def test_currency_is_fixed_once_invoiced(api, acme):
    cid = acme["client"]["id"]
    line = {"description": "Logo", "quantity_hundredths": 100, "unit_price_minor": 1000}
    api.post("/api/invoices", json={"client_id": cid, "lines": [line]})
    assert (
        api.put(f"/api/clients/{cid}", json={"name": "Acme", "currency": "USD"}).status_code == 409
    )
    assert (
        api.put(f"/api/clients/{cid}", json={"name": "Acme", "currency": "TRY"}).status_code == 200
    )


def test_projects_report_currency_and_unbilled_time(api, acme):
    pid = acme["project"]["id"]
    api.post("/api/time", json={"project_id": pid, "date": TODAY, "minutes": 90})
    api.post("/api/time", json={"project_id": pid, "date": TODAY, "minutes": 30, "billable": False})
    [project] = api.get("/api/projects").json()
    assert project["client_name"] == "Acme Yazılım"
    assert project["currency"] == "TRY"
    assert project["unbilled_minutes"] == 90
    assert api.post("/api/projects", json={"client_id": 999, "name": "X"}).status_code == 404
    assert api.delete(f"/api/projects/{pid}").status_code == 409  # has tracked time
    archived = api.put(f"/api/projects/{pid}", json={"name": "Website", "archived": True})
    assert archived.json()["archived"] is True


def test_manual_time_entries(api, acme):
    pid = acme["project"]["id"]
    for minutes in (0, -5, 24 * 60 + 1):
        body = {"project_id": pid, "date": TODAY, "minutes": minutes}
        assert api.post("/api/time", json=body).status_code == 422
    entry = api.post(
        "/api/time",
        json={"project_id": pid, "date": "2026-03-02", "minutes": 75, "description": "Wireframes"},
    ).json()
    assert entry["project_name"] == "Website" and entry["client_name"] == "Acme Yazılım"

    edited = api.put(
        f"/api/time/{entry['id']}", json={"project_id": pid, "date": "2026-03-03", "minutes": 60}
    ).json()
    assert (edited["date"], edited["minutes"], edited["description"]) == ("2026-03-03", 60, "")

    assert len(api.get("/api/time", params={"date_from": "2026-03-03"}).json()) == 1
    assert api.get("/api/time", params={"date_to": "2026-03-02"}).json() == []
    assert api.delete(f"/api/time/{entry['id']}").status_code == 204
    assert api.get("/api/time").json() == []


def test_timer_start_stop(api, acme):
    pid = acme["project"]["id"]
    assert api.get("/api/timer").json() is None
    assert api.post("/api/timer/stop").status_code == 409

    started = api.post("/api/timer/start", json={"project_id": pid, "description": "Call"})
    assert started.status_code == 201 and started.json()["started_at"]
    assert api.get("/api/timer").json()["id"] == started.json()["id"]
    assert (
        api.post("/api/timer/start", json={"project_id": pid}).status_code == 409
    )  # one at a time
    assert api.get("/api/time").json() == []  # a running timer is not a finished entry yet

    stopped = api.post("/api/timer/stop").json()
    assert stopped["started_at"] is None
    assert stopped["minutes"] == 1  # rounded up to the minimum
    assert stopped["date"] == TODAY
    assert api.get("/api/timer").json() is None
    assert [e["id"] for e in api.get("/api/time").json()] == [stopped["id"]]


def test_timer_refuses_archived_project(api, acme):
    pid = acme["project"]["id"]
    api.put(f"/api/projects/{pid}", json={"name": "Website", "archived": True})
    assert api.post("/api/timer/start", json={"project_id": pid}).status_code == 409


JSON = {"content-type": "application/json"}


def test_text_that_cannot_be_stored_is_a_422_not_a_server_error(api, anon):
    # a lone surrogate is valid JSON but cannot be encoded as UTF-8
    assert api.post("/api/clients", content=b'{"name": "\\ud800"}', headers=JSON).status_code == 422
    login = anon.post("/api/auth/login", content=b'{"password": "\\ud800x"}', headers=JSON)
    assert login.status_code == 422


def test_an_id_too_big_for_sqlite_is_a_404_or_422(api):
    huge = 10**30
    assert api.post("/api/projects", json={"client_id": huge, "name": "p"}).status_code in (
        404,
        422,
    )
    assert api.get(f"/api/invoices/{huge}").status_code in (404, 422)
    assert api.post("/api/invoices", json={"client_id": huge}).status_code in (404, 422)
    assert api.post(
        "/api/time", json={"project_id": huge, "date": "2026-01-01", "minutes": 5}
    ).status_code in (404, 422)
    assert api.post("/api/timer/start", json={"project_id": huge}).status_code in (404, 422)
    assert api.get(f"/api/time?project_id={huge}").status_code == 200
