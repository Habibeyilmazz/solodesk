import datetime as dt
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from . import models  # noqa: F401  (registers the tables)
from .models import Settings


def make_engine(db_path: Path | str):
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 15}
    )

    @event.listens_for(engine, "connect")
    def _connect(conn, _record):
        conn.isolation_level = None  # we issue BEGIN ourselves, below
        conn.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def _begin(conn):
        # Every request runs alone, start to finish. Rules like "only drafts can be edited",
        # "one running timer" and "the next invoice number" are check-then-write, and with
        # SQLite's default deferred transactions two requests could both pass the check.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

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
