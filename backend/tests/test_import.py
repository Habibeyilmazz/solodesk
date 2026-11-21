"""Importing a Toggl Track detailed report."""

HEADER = (
    "User,Email,Client,Project,Task,Description,Billable,Start date,Start time,"
    "End date,End time,Duration,Tags,Amount (EUR)\n"
)


def toggl(*rows: str) -> str:
    return "﻿" + HEADER + "".join(r + "\n" for r in rows)


def row(client="Acme Yazılım", project="Website", desc="Header fix", billable="Yes",
        date="2025-03-04", duration="01:30:00") -> str:  # fmt: skip
    return (
        f'Demo,demo@example.test,{client},{project},,"{desc}",{billable},{date},09:00:00,'
        f"{date},10:30:00,{duration},,90.00"
    )


def test_import_matches_existing_names_and_creates_missing(api, acme):
    csv = toggl(
        row(client="acme yazılım", project="WEBSITE"),  # matched, ignoring case
        row(
            project="Logo", duration="00:00:20", billable="No", date="2025-01-15"
        ),  # new project, rounds up to 1m
        row(client="Kuzey Kafe", project="Menu", desc="Menu, with a comma", duration="25:00:00"),
    )
    r = api.post("/api/import/toggl", json={"csv": csv, "currency": "EUR"})
    assert r.status_code == 422
    assert "row 4: an entry can be at most 24 hours" in r.json()["detail"]
    assert api.get("/api/time").json() == []  # all or nothing

    csv = csv.replace("25:00:00", "02:15:59")
    r = api.post("/api/import/toggl", json={"csv": csv, "currency": "EUR"})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "dry_run": False,
        "added": 3,
        "minutes": 90 + 1 + 136,
        "skipped_duplicates": 0,
        "earliest_date": "2025-01-15",  # the oldest added entry
        "new_clients": ["Kuzey Kafe"],
        "new_projects": ["Acme Yazılım: Logo", "Kuzey Kafe: Menu"],
    }
    entries = {e["project_name"]: e for e in api.get("/api/time").json()}
    assert entries["Website"]["project_id"] == acme["project"]["id"]
    assert entries["Website"]["minutes"] == 90 and entries["Website"]["date"] == "2025-03-04"
    assert entries["Logo"]["billable"] is False
    assert entries["Menu"]["description"] == "Menu, with a comma"
    kafe = next(c for c in api.get("/api/clients").json() if c["name"] == "Kuzey Kafe")
    assert kafe["currency"] == "EUR"


def test_importing_the_same_file_twice_adds_nothing(api, acme):
    csv = toggl(row(), row())  # two identical rows in one file are two entries
    assert api.post("/api/import/toggl", json={"csv": csv}).json()["added"] == 2
    again = api.post("/api/import/toggl", json={"csv": csv}).json()
    assert again["added"] == 0 and again["skipped_duplicates"] == 2
    assert again["earliest_date"] is None
    assert len(api.get("/api/time").json()) == 2


def test_dry_run_reports_without_saving(api, acme):
    csv = toggl(row(client="", project=""), row(client="New Co", project="Audit"))
    r = api.post("/api/import/toggl", json={"csv": csv, "dry_run": True}).json()
    assert r["dry_run"] is True and r["added"] == 2
    assert r["new_clients"] == ["No client", "New Co"]
    assert api.get("/api/time").json() == []
    assert len(api.get("/api/clients").json()) == 1


def test_bad_files_are_refused_with_reasons(api):
    def detail(csv):
        r = api.post("/api/import/toggl", json={"csv": csv})
        assert r.status_code == 422
        return r.json()["detail"]

    assert "no 'Duration' column" in detail("Project,Start date\nWebsite,2025-01-01\n")
    assert "no time entries" in detail(toggl())
    assert "row 2: start date '04/03/2025' is not like" in detail(toggl(row(date="04/03/2025")))
    assert "outside 1970-2100" in detail(toggl(row(date="1900-01-01")))
    assert "duration '1h30m' is not like" in detail(toggl(row(duration="1h30m")))
    many = detail(toggl(*[row(duration="x")] * 15))
    assert "and 5 more" in many
    assert "cannot be read" in detail(HEADER + '"' + "a" * 200_000 + '"\n')


def test_import_needs_sign_in(anon):
    assert anon.post("/api/import/toggl", json={"csv": toggl(row())}).status_code == 401


def test_semicolon_separated_files_are_read(api):
    # Excel in many locales saves a re-opened CSV with semicolons
    csv = "Client;Project;Description;Start date;Duration\nAcme;Site;a, b;2025-01-02;01:30:00\n"
    r = api.post("/api/import/toggl", json={"csv": csv})
    assert r.status_code == 200 and (r.json()["added"], r.json()["minutes"]) == (1, 90)
    assert api.get("/api/time").json()[0]["description"] == "a, b"
