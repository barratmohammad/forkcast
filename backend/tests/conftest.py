"""Shared pytest fixtures for the ForkCast backend."""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")
# Fake bag-of-words embeddings are less tight than real ones, so loosen the guardrail.
os.environ.setdefault("RAG_MAX_DISTANCE", "0.85")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401  (registers tables on Base.metadata)
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
def fake_llm():
    """A fresh FakeLLM per test."""
    from tests.fakes import FakeLLM

    return FakeLLM()


@pytest.fixture
def index(fake_llm):
    """A RecipeIndex on an in-memory Chroma collection unique to this test."""
    import uuid

    import chromadb

    from rag_pipeline import RecipeIndex

    chroma = chromadb.EphemeralClient(chromadb.Settings(anonymized_telemetry=False))
    idx = RecipeIndex(chroma, fake_llm, collection_name=f"test_{uuid.uuid4().hex}")
    yield idx
    chroma.delete_collection(idx.collection_name)


@pytest.fixture
def client(db_session, fake_llm, index):
    """TestClient with the DB dependency pointed at the in-memory test database."""
    from fastapi.testclient import TestClient

    from database import get_db
    from main import create_app
    from ollama_client import get_llm
    from rag_pipeline import get_index

    app = create_app(seed=False)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_llm] = lambda: fake_llm
    app.dependency_overrides[get_index] = lambda: index
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
