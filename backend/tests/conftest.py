"""Shared pytest fixtures for the ForkCast backend."""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base


@pytest.fixture
def db_session():
    """Yield a session bound to a fresh in-memory SQLite database."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    """TestClient with the DB dependency pointed at the in-memory test database."""
    from fastapi.testclient import TestClient

    from database import get_db
    from main import create_app

    app = create_app(seed=False)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        c.app_ref = app
        yield c


@pytest.fixture
def auth_headers(client):
    """Factory: register + log in a user, return Authorization headers."""

    def _make(username: str = "alice", password: str = "supersecret") -> dict:
        client.post("/auth/register", json={"username": username, "password": password})
        resp = client.post("/auth/token", data={"username": username, "password": password})
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _make
