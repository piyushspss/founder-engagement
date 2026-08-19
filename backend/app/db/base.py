"""SQLite engine/session wiring. One file, no ORM cleverness.

PLAN §6: SQLAlchemy + SQLite, single process, no concurrency story needed.
The DB path is env-overridable so tests get a throwaway file/in-memory DB and
never touch the developer's `founder.db`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_URL = f"sqlite:///{REPO_ROOT / 'founder.db'}"


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for every table in the app."""

    pass


_engine = None
_SessionLocal = None


def database_url() -> str:
    """`FOUNDER_DB_URL` if set, else the repo-local SQLite file.

    SQLite is an MVP tradeoff — one writer, one machine — not a production
    concurrency story."""
    return os.environ.get("FOUNDER_DB_URL", DEFAULT_URL)


def get_engine():
    """The process-wide engine and session factory, created once."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(database_url(), future=True,
                                connect_args={"check_same_thread": False})
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False,
                                     future=True)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine so a changed FOUNDER_DB_URL takes effect (tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(drop: bool = False) -> None:
    """Create tables. Idempotent; `drop=True` rebuilds from scratch (tests)."""
    from app.db import models  # noqa: F401  (register mappers)

    engine = get_engine()
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def session_factory():
    """The configured sessionmaker, initialising the engine on first use."""
    get_engine()
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction boundary. Commit on clean exit, roll back on any exception —
    this is what makes 'a failed rescore mutates nothing' true rather than
    aspirational."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
