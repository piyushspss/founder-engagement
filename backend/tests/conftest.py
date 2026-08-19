import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def pytest_configure():
    pass


# --------------------------------------------------------------- CP7 fixtures
@pytest.fixture()
def db_url(tmp_path, monkeypatch):
    """A throwaway SQLite file per test. Never the developer's founder.db."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("FOUNDER_DB_URL", url)
    from app.db import base
    base.reset_engine()
    base.init_db(drop=True)
    yield url
    base.reset_engine()


@pytest.fixture()
def client(db_url):
    from fastapi.testclient import TestClient

    from app.api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def session(db_url):
    from app.db.base import session_factory
    s = session_factory()()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def raw_population():
    return json.loads((ROOT / "data" / "synthetic" / "load_800.json").read_text())


@pytest.fixture()
def sample_profiles(raw_population):
    """A small, deterministic slice — includes the duplicate-bearing records."""
    return raw_population[:25]


@pytest.fixture()
def seeded(client, sample_profiles):
    r = client.post("/import", json={"profiles": sample_profiles, "source": "test",
                                     "funnel": "TEST"})
    assert r.status_code == 200, r.text
    return r.json()
