from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from ..deps import get_db, get_or_404
from ..models import (
    Client,
    ClientIn,
    Invoice,
    InvoiceLine,
    Project,
    ProjectIn,
    ProjectUpdate,
    TimeEntry,
)

router = APIRouter(prefix="/api", tags=["clients and projects"])


@router.get("/clients")
def list_clients(db: Session = Depends(get_db)) -> list[Client]:
    return db.exec(select(Client).order_by(func.lower(Client.name))).all()


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, db: Session = Depends(get_db)) -> Client:
    client = Client(**body.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.put("/clients/{client_id}")
def update_client(client_id: int, body: ClientIn, db: Session = Depends(get_db)) -> Client:
    client = get_or_404(db, Client, client_id)
    if (
        body.currency != client.currency
        and db.exec(select(Invoice.id).where(Invoice.client_id == client_id).limit(1)).first()
    ):
        raise HTTPException(409, "This client already has invoices, so its currency is fixed.")
    client.sqlmodel_update(body.model_dump())
    db.commit()
    db.refresh(client)
    return client


@router.delete("/clients/{client_id}", status_code=204)
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = get_or_404(db, Client, client_id)
    has_projects = db.exec(
        select(Project.id).where(Project.client_id == client_id).limit(1)
    ).first()
    has_invoices = db.exec(
        select(Invoice.id).where(Invoice.client_id == client_id).limit(1)
    ).first()
    if has_projects or has_invoices:
        raise HTTPException(409, "Delete this client's projects and invoices first.")
    db.delete(client)
    db.commit()


def project_out(project: Project, client: Client, unbilled_minutes: int = 0) -> dict:
    return {
        **project.model_dump(),
        "client_name": client.name,
        "currency": client.currency,
        "unbilled_minutes": unbilled_minutes,
    }


@router.get("/projects")
def list_projects(client_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    unbilled = dict(
        db.exec(
            select(TimeEntry.project_id, func.sum(TimeEntry.minutes))
            .where(TimeEntry.billable, TimeEntry.invoice_id.is_(None))
            .group_by(TimeEntry.project_id)
        ).all()
    )
    query = select(Project, Client).join(Client, Project.client_id == Client.id)
    if client_id is not None:
        query = query.where(Project.client_id == client_id)
    rows = db.exec(
        query.order_by(Project.archived, func.lower(Client.name), func.lower(Project.name))
    )
    return [project_out(p, c, unbilled.get(p.id, 0)) for p, c in rows]


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db)) -> dict:
    client = get_or_404(db, Client, body.client_id)
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_out(project, client)


@router.put("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)) -> dict:
    project = get_or_404(db, Project, project_id)
    project.sqlmodel_update(body.model_dump())
    db.commit()
    db.refresh(project)
    return project_out(project, db.get(Client, project.client_id))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = get_or_404(db, Project, project_id)
    if db.exec(select(TimeEntry.id).where(TimeEntry.project_id == project_id).limit(1)).first():
        raise HTTPException(409, "This project has tracked time. Archive it instead.")
    if db.exec(select(InvoiceLine.id).where(InvoiceLine.project_id == project_id).limit(1)).first():
        raise HTTPException(409, "This project is on an invoice. Archive it instead.")
    db.delete(project)
    db.commit()
