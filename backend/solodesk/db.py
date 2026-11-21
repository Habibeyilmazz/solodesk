import datetime as dt
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from . import models  # noqa: F401  (registers the tables)
from .models import Settings


def make_engine(db_path: Path | str):
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _record):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")

    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        if db.get(Settings, 1) is None:
            db.add(Settings(id=1))
            db.commit()
    return engine


def today() -> dt.date:
    """The server's local date. Set TZ to control where midnight falls."""
    return dt.date.today()


__all__ = ["Session", "make_engine", "select", "today"]
