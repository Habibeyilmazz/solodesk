import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import today
from ..deps import get_db, get_or_404
from ..models import Client, Invoice, Project, TimeEntry, TimeEntryIn, TimerStartIn, utcnow

router = APIRouter(prefix="/api", tags=["time"])
MAX_MINUTES = 24 * 60


def entry_out(entry: TimeEntry, project: Project, client: Client, invoice_number=None) -> dict:
    return {
        **entry.model_dump(),
        "project_name": project.name,
        "client_id": client.id,
        "client_name": client.name,
        "invoice_number": invoice_number,
    }


def _joined():
    return (
        select(TimeEntry, Project, Client, Invoice.number)
        .join(Project, TimeEntry.project_id == Project.id)
        .join(Client, Project.client_id == Client.id)
        .join(Invoice, TimeEntry.invoice_id == Invoice.id, isouter=True)
    )


def _one(db: Session, entry_id: int) -> dict:
    return entry_out(*db.exec(_joined().where(TimeEntry.id == entry_id)).one())


@router.get("/time")
def list_time(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    project_id: int | None = None,
    client_id: int | None = None,
    unbilled: bool = False,
    limit: int = 500,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Finished entries, newest first. `unbilled` keeps billable entries not yet on an invoice."""
    query = _joined().where(TimeEntry.started_at.is_(None))
    if date_from:
        query = query.where(TimeEntry.date >= date_from)
    if date_to:
        query = query.where(TimeEntry.date <= date_to)
    if project_id is not None:
        query = query.where(TimeEntry.project_id == project_id)
    if client_id is not None:
        query = query.where(Project.client_id == client_id)
    if unbilled:
        query = query.where(TimeEntry.billable, TimeEntry.invoice_id.is_(None))
    query = query.order_by(TimeEntry.date.desc(), TimeEntry.id.desc()).limit(
        min(max(limit, 1), 5000)
    )
    return [entry_out(*row) for row in db.exec(query)]


@router.post("/time", status_code=201)
def create_entry(body: TimeEntryIn, db: Session = Depends(get_db)) -> dict:
    get_or_404(db, Project, body.project_id)
    entry = TimeEntry(**body.model_dump())
    db.add(entry)
    db.commit()
    return _one(db, entry.id)


def _editable(db: Session, entry_id: int) -> TimeEntry:
    entry = get_or_404(db, TimeEntry, entry_id)
    if entry.invoice_id is not None:
        raise HTTPException(409, "This entry is on an invoice and can no longer be changed.")
    return entry


@router.put("/time/{entry_id}")
def update_entry(entry_id: int, body: TimeEntryIn, db: Session = Depends(get_db)) -> dict:
    entry = _editable(db, entry_id)
    if entry.started_at is not None:
        raise HTTPException(409, "Stop the timer before editing this entry.")
    get_or_404(db, Project, body.project_id)
    entry.sqlmodel_update(body.model_dump())
    db.commit()
    return _one(db, entry.id)


@router.delete("/time/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    db.delete(_editable(db, entry_id))
    db.commit()


def _running(db: Session) -> TimeEntry | None:
    return db.exec(select(TimeEntry).where(TimeEntry.started_at.is_not(None))).first()


@router.get("/timer")
def get_timer(db: Session = Depends(get_db)) -> dict | None:
    """The running timer, or null."""
    entry = _running(db)
    return _one(db, entry.id) if entry else None


@router.post("/timer/start", status_code=201)
def start_timer(body: TimerStartIn, db: Session = Depends(get_db)) -> dict:
    if _running(db):
        raise HTTPException(409, "A timer is already running. Stop it first.")
    project = get_or_404(db, Project, body.project_id)
    if project.archived:
        raise HTTPException(409, "This project is archived.")
    entry = TimeEntry(**body.model_dump(), date=today(), started_at=utcnow())
    db.add(entry)
    db.commit()
    return _one(db, entry.id)


@router.post("/timer/stop")
def stop_timer(db: Session = Depends(get_db)) -> dict:
    entry = _running(db)
    if entry is None:
        raise HTTPException(409, "No timer is running.")
    elapsed = (utcnow() - entry.started_at).total_seconds()
    # at least a minute so the entry is visible; at most a day so a forgotten timer stays sane
    entry.minutes = min(max(round(elapsed / 60), 1), MAX_MINUTES)
    entry.started_at = None
    db.commit()
    return _one(db, entry.id)
