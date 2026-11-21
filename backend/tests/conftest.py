import pytest
from fastapi.testclient import TestClient

from solodesk.auth import hash_password
from solodesk.config import Config
from solodesk.main import create_app

PASSWORD = "correct horse battery"
PASSWORD_HASH = hash_password(PASSWORD)  # hashed once: scrypt is deliberately slow


@pytest.fixture
def app(tmp_path):
    return create_app(Config(db_path=tmp_path / "test.db", password_hash=PASSWORD_HASH))


@pytest.fixture
def anon(app):
    """A client that has not signed in."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def api(app):
    """A signed-in client that sends the CSRF token on every request."""
    with TestClient(app) as client:
        csrf = client.post("/api/auth/login", json={"password": PASSWORD}).json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf
        yield client


@pytest.fixture
def acme(api):
    """A client with one project at 1,500.00 TRY per hour."""
    client = api.post("/api/clients", json={"name": "Acme Yazılım", "currency": "TRY"}).json()
    project = api.post(
        "/api/projects",
        json={"client_id": client["id"], "name": "Website", "hourly_rate_minor": 150_000},
    ).json()
    return {"client": client, "project": project}
