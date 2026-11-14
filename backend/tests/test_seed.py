"""Seed loading, startup indexing and reindex tests."""

import json

import pytest
from sqlalchemy import func, select

from models import Recipe
from seed import ensure_system_user, load_seed_recipes, sync_index
from tests.payloads import CURRY


@pytest.fixture
def seed_file(tmp_path):
    """A two-recipe seed file in TheMealDB-derived format."""
    path = tmp_path / "seed.json"
    path.write_text(
        json.dumps(
            [
                {
                    "title": "Shakshuka",
                    "category": "Vegetarian",
                    "cuisine": "Egyptian",
                    "ingredients": [{"name": "eggs", "measure": "4"}],
                    "instructions": "Simmer tomatoes and peppers, crack in eggs, cover and cook.",
                    "source_url": "",
                },
                {
                    "title": "Lamb Tagine",
                    "category": "Lamb",
                    "cuisine": "Moroccan",
                    "ingredients": [{"name": "lamb shoulder", "measure": "1kg"}],
                    "instructions": "Brown the lamb, add spices and apricots, braise slowly.",
                    "source_url": "",
                },
            ]
        )
    )
    return path


def test_load_seed_is_idempotent(db_session, seed_file):
    assert load_seed_recipes(db_session, seed_file) == 2
    assert load_seed_recipes(db_session, seed_file) == 0
    assert db_session.scalar(select(func.count(Recipe.id))) == 2
    shakshuka = db_session.scalar(select(Recipe).where(Recipe.title == "Shakshuka"))
    assert shakshuka.source == "seed"
    assert shakshuka.owner.username == "forkcast"
    assert "vegetarian" in shakshuka.tag_names


def test_sync_index_only_adds_missing(db_session, seed_file, index):
    load_seed_recipes(db_session, seed_file)
    assert sync_index(db_session, index) == 2
    assert sync_index(db_session, index) == 0
    assert index.count() == 2


def test_sync_index_tolerates_ollama_down(db_session, seed_file, index, fake_llm):
    load_seed_recipes(db_session, seed_file)
    fake_llm.down = True
    assert sync_index(db_session, index) == 0


def test_system_user_cannot_login(client, db_session):
    ensure_system_user(db_session)
    r = client.post("/auth/token", data={"username": "forkcast", "password": "!"})
    assert r.status_code == 401


def test_reindex_endpoint(client, auth_headers, index):
    h = auth_headers()
    client.post("/recipes", json=CURRY, headers=h)
    index.reset()
    assert index.count() == 0
    r = client.post("/admin/reindex", headers=h)
    assert r.status_code == 200
    assert r.json() == {"indexed": 1}
    assert index.count() == 1


def test_reindex_keeps_index_when_ollama_down(client, auth_headers, index, fake_llm):
    h = auth_headers()
    client.post("/recipes", json=CURRY, headers=h)
    fake_llm.down = True
    assert client.post("/admin/reindex", headers=h).status_code == 503
    assert index.count() == 1


def test_background_indexer_heals_after_ollama_returns(db_session, seed_file, index, fake_llm):
    import threading
    import time

    from seed import run_indexer

    load_seed_recipes(db_session, seed_file)
    fake_llm.down = True
    stop = threading.Event()
    thread = threading.Thread(
        target=run_indexer, args=(lambda: db_session, index, 0.05, stop), daemon=True
    )
    thread.start()
    time.sleep(0.2)
    assert index.count() == 0
    fake_llm.down = False
    deadline = time.time() + 5
    while index.count() < 2 and time.time() < deadline:
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=2)
    assert index.count() == 2
    assert not thread.is_alive()
