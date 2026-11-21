"""Import time entries from a Toggl Track detailed report (CSV)."""

import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..deps import get_db
from ..models import Client, Project, TimeEntry, TogglImportIn
from .time import MAX_MINUTES

router = APIRouter(prefix="/api/import", tags=["import"])
NO_CLIENT = "No client"
NO_PROJECT = "No project"
MAX_ERRORS = 10


def _minutes(duration: str) -> int:
    """Toggl's 'HH:MM:SS' (hours may pass 24) to whole minutes, at least one."""
    parts = duration.strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        raise ValueError(f"duration '{duration}' is not like 01:30:00")
    hours, minutes, seconds = (int(p) for p in (parts + ["0"])[:3])
    if minutes > 59 or seconds > 59:
        raise ValueError(f"duration '{duration}' is not like 01:30:00")
    total = max(round((hours * 3600 + minutes * 60 + seconds) / 60), 1)
    if total > MAX_MINUTES:
        raise ValueError("an entry can be at most 24 hours")
    return total


def _date(text: str) -> dt.date:
    try:
        date = dt.date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"start date '{text}' is not like 2025-01-31") from None
    if not dt.date(1970, 1, 1) <= date <= dt.date(2100, 12, 31):
        raise ValueError(f"start date '{text}' is outside 1970-2100")
    return date


def parse_toggl(text: str) -> list[dict]:
    """Rows of a Toggl CSV as entry fields. Raises HTTPException 422 listing bad rows."""
    reader = csv.DictReader(io.StringIO(text.removeprefix("\ufeff")))
    columns = {name.strip().lower(): name for name in reader.fieldnames or []}
    missing = [c for c in ("project", "start date", "duration") if c not in columns]
    if missing:
        raise HTTPException(
            422,
            "This does not look like a Toggl Track detailed report: no "
            + ", ".join(f"'{c.title()}'" for c in missing)
            + (" columns" if len(missing) > 1 else " column")
            + ". Export it from Reports, Detailed, as CSV.",
        )

    def cell(row: dict, name: str) -> str:
        return (row.get(columns.get(name, ""), "") or "").strip()

    rows, errors = [], []
    try:
        rows_in = list(reader)
    except csv.Error as e:  # e.g. a cell over csv's 128 KB field limit
        raise HTTPException(422, f"Line {reader.line_num} cannot be read: {e}") from None
    for line, row in enumerate(rows_in, start=2):
        try:
            date = _date(cell(row, "start date"))
            rows.append(
                {
                    "client": cell(row, "client")[:200] or NO_CLIENT,
                    "project": cell(row, "project")[:200] or NO_PROJECT,
                    "date": date,
                    "minutes": _minutes(cell(row, "duration")),
                    "description": cell(row, "description")[:500],
                    "billable": cell(row, "billable").lower() not in ("no", "false", "0"),
                }
            )
        except ValueError as e:
            errors.append(f"row {line}: {e}")
    if errors:
        more = len(errors) - MAX_ERRORS
        raise HTTPException(
            422,
            "Nothing was imported. "
            + "; ".join(errors[:MAX_ERRORS])
            + (f"; and {more} more" if more > 0 else ""),
        )
    if not rows:
        raise HTTPException(422, "The file has no time entries.")
    return rows


@router.post("/toggl")
def import_toggl(body: TogglImportIn, db: Session = Depends(get_db)) -> dict:
    """Add the entries of a Toggl Track detailed report (CSV text in `csv`).

    Clients and projects are matched by name, ignoring case, and created when missing (new
    clients get `currency`, new projects an hourly rate of 0). An entry already in solodesk
    with the same project, date, minutes and description is skipped, so importing the same
    file twice adds nothing. With `dry_run` the counts are returned and nothing is saved.
    All or nothing: one bad row and no entry is added.
    """
    rows = parse_toggl(body.csv)
    clients = {c.name.lower(): c for c in db.exec(select(Client)).all()}
    projects = {(p.client_id, p.name.lower()): p for p in db.exec(select(Project)).all()}
    existing = {
        (e.project_id, e.date, e.minutes, e.description)
        for e in db.exec(select(TimeEntry).where(TimeEntry.started_at.is_(None))).all()
    }
    new_clients, new_projects = [], []
    added = skipped = minutes = 0
    for row in rows:
        client = clients.get(row["client"].lower())
        if client is None:
            client = Client(name=row["client"], currency=body.currency)
            db.add(client)
            db.flush()
            clients[client.name.lower()] = client
            new_clients.append(client.name)
        project = projects.get((client.id, row["project"].lower()))
        if project is None:
            project = Project(client_id=client.id, name=row["project"])
            db.add(project)
            db.flush()
            projects[(client.id, project.name.lower())] = project
            new_projects.append(f"{client.name}: {project.name}")
        key = (project.id, row["date"], row["minutes"], row["description"])
        if key in existing:
            skipped += 1
            continue
        db.add(
            TimeEntry(
                project_id=project.id,
                date=row["date"],
                minutes=row["minutes"],
                description=row["description"],
                billable=row["billable"],
            )
        )
        added += 1
        minutes += row["minutes"]
    if body.dry_run:
        db.rollback()
    else:
        db.commit()
    return {
        "dry_run": body.dry_run,
        "added": added,
        "minutes": minutes,
        "skipped_duplicates": skipped,
        "new_clients": new_clients,
        "new_projects": new_projects,
    }
