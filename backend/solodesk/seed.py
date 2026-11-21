"""Fill an empty database with demo data: python -m solodesk.seed

Everything is invented and dated relative to today, so the dashboard always looks lived-in.
"""

import datetime as dt
import random
import sys

from sqlmodel import Session, select

from .config import db_path_from_env
from .db import make_engine, today
from .models import Client, Invoice, InvoiceLine, Project, Settings, TimeEntry
from .routers.invoices import _lines_from_time, _recalculate

MONTHS_BACK = 8

# (client, [(project, hourly rate in minor units, [task descriptions])])
CLIENTS = [
    (
        Client(
            name="Kuzey Mimarlık",
            email="muhasebe@kuzeymimarlik.example",
            address="Örnek Cad. No: 112\nKadıköy, İstanbul",
            tax_id="1234567890",
            currency="TRY",
        ),
        [
            (
                "Web sitesi yenileme",
                180_000,
                ["Ana sayfa tasarımı", "Proje galerisi", "İçerik taşıma", "Revizyonlar"],
            ),
            (
                "Bakım ve destek",
                150_000,
                ["Güncellemeler", "Yedekleme kontrolü", "Küçük düzeltmeler"],
            ),
        ],
    ),
    (
        Client(
            name="Brightwell Studio",
            email="accounts@brightwell.example",
            address="14 Example Lane\nBristol BS1 9ZZ",
            currency="GBP",
        ),
        [
            (
                "Design system",
                6_500,
                ["Component audit", "Tokens and theming", "Docs site", "Review call"],
            )
        ],
    ),
    (
        Client(
            name="Northwind Labs",
            email="ap@northwindlabs.example",
            address="500 Sample Street, Suite 12\nPortland, OR 97201",
            currency="USD",
        ),
        [
            (
                "Mobile app",
                8_500,
                ["Onboarding flow", "Push notifications", "Bug fixes", "Release build"],
            ),
            (
                "API integration",
                9_500,
                ["Webhook handlers", "Rate limit handling", "Integration tests"],
            ),
        ],
    ),
    (
        Client(
            name="Atelier Lumen",
            email="compta@atelierlumen.example",
            address="8 rue de l'Exemple\n69002 Lyon",
            currency="EUR",
        ),
        [
            (
                "Online shop",
                7_000,
                ["Product pages", "Checkout tweaks", "Shipping rules", "Newsletter signup"],
            )
        ],
    ),
    (
        Client(
            name="Ege Kahve Kavurma",
            email="merhaba@egekahve.example",
            address="Örnek Sk. No: 9\nUrla, İzmir",
            tax_id="9876543210",
            currency="TRY",
        ),
        [
            (
                "Marka kimliği",
                160_000,
                ["Logo çalışmaları", "Ambalaj tasarımı", "Sosyal medya şablonları"],
            )
        ],
    ),
]

EXTRAS = [("Domain and hosting, 1 year", 240_000), ("Stock photography licence", 95_000)]


def month_start(on: dt.date, back: int) -> dt.date:
    index = on.year * 12 + on.month - 1 - back
    return dt.date(index // 12, index % 12 + 1, 1)


def seed(db: Session, on: dt.date) -> None:
    rng = random.Random(4150)
    settings = db.get(Settings, 1)
    settings.sqlmodel_update(
        {
            "business_name": "Mavi Fener Studio",
            "business_address": "Örnek Mah. 12. Sk. No: 4\nKonak, İzmir",
            "business_email": "hello@mavifener.example",
            "tax_id": "1112223334",
            "invoice_footer": "Bank transfer: TR00 0000 0000 0000 0000 0000 00 (Example Bank)",
        }
    )

    projects: list[tuple[Project, list[str]]] = []
    clients: list[Client] = []
    for client, client_projects in CLIENTS:
        client = Client(**client.model_dump(exclude={"id", "created_at"}))
        db.add(client)
        db.flush()
        clients.append(client)
        for name, rate, tasks in client_projects:
            project = Project(client_id=client.id, name=name, hourly_rate_minor=rate)
            db.add(project)
            projects.append((project, tasks))
    db.flush()

    # a couple of sessions on most working days
    day = month_start(on, MONTHS_BACK)
    while day <= on:
        if day.weekday() < 5 and rng.random() < 0.9:
            for project, tasks in rng.sample(projects, k=rng.choice((1, 2, 2, 3))):
                db.add(
                    TimeEntry(
                        project_id=project.id,
                        date=day,
                        minutes=rng.choice((45, 60, 90, 90, 120, 150, 180)),
                        description=rng.choice(tasks),
                        billable=rng.random() < 0.94,
                    )
                )
        day += dt.timedelta(days=1)
    db.flush()

    # one invoice per client per finished month, numbered in the order they were issued
    last_month_fate = ["paid", "sent", "overdue", "sent", "paid"]
    number = 0
    for back in range(MONTHS_BACK, 0, -1):
        first, after = month_start(on, back), month_start(on, back - 1)
        for index, client in enumerate(clients):
            ids = unbilled_ids(db, client.id, first, after)
            if not ids:
                continue
            fate = last_month_fate[index] if back == 1 else "paid"
            issue = after
            due = issue + dt.timedelta(days=14)
            if fate == "sent":
                due = on + dt.timedelta(days=4 + 3 * index)
                issue = min(issue, due - dt.timedelta(days=14))
            elif fate == "overdue":
                due = on - dt.timedelta(days=6)
                issue = due - dt.timedelta(days=14)
            invoice = Invoice(
                client_id=client.id,
                currency=client.currency,
                issue_date=issue,
                due_date=due,
                tax_rate_bp=2000 if client.currency == "TRY" else 0,
                discount_bp=500 if (back, index) == (3, 2) else 0,
                notes="Thank you for your business.",
            )
            db.add(invoice)
            db.flush()
            lines = _lines_from_time(db, invoice, ids)
            if client.currency == "TRY" and back in (5, 2) and index == 0:
                description, price = EXTRAS[back % 2]
                lines.append(
                    InvoiceLine(
                        invoice_id=invoice.id,
                        description=description,
                        quantity_hundredths=100,
                        unit_price_minor=price,
                        amount_minor=0,
                    )
                )
            _recalculate(invoice, lines)
            db.add_all(lines)
            number += 1
            invoice.number = f"{settings.invoice_prefix}{number:04d}"
            invoice.status = "paid" if fate == "paid" else "sent"
            if fate == "paid":
                invoice.paid_on = min(issue + dt.timedelta(days=rng.randint(3, 16)), on)
    settings.next_invoice_number = number + 1

    # this month's work so far for the first client, waiting as a draft
    ids = unbilled_ids(db, clients[0].id, month_start(on, 0), on + dt.timedelta(days=1))
    if ids:
        draft = Invoice(
            client_id=clients[0].id,
            currency=clients[0].currency,
            issue_date=on,
            due_date=on + dt.timedelta(days=14),
            tax_rate_bp=2000,
        )
        db.add(draft)
        db.flush()
        lines = _lines_from_time(db, draft, ids)
        _recalculate(draft, lines)
        db.add_all(lines)
    db.commit()


def unbilled_ids(db: Session, client_id: int, first: dt.date, after: dt.date) -> list[int]:
    return db.exec(
        select(TimeEntry.id)
        .join(Project, TimeEntry.project_id == Project.id)
        .where(
            Project.client_id == client_id,
            TimeEntry.billable,
            TimeEntry.invoice_id.is_(None),
            TimeEntry.date >= first,
            TimeEntry.date < after,
        )
    ).all()


def main() -> None:
    path = db_path_from_env()
    with Session(make_engine(path)) as db:
        if db.exec(select(Client.id).limit(1)).first():
            sys.exit(f"{path} already has data. Delete the file first if you want fresh demo data.")
        seed(db, today())
        counts = {
            model.__name__: len(db.exec(select(model.id)).all())
            for model in (Client, Project, TimeEntry, Invoice)
        }
    print(f"Seeded {path}: " + ", ".join(f"{n} {name.lower()} rows" for name, n in counts.items()))


if __name__ == "__main__":
    main()
