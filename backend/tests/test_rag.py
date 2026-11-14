"""Tests for the /ask RAG endpoint and its guardrails."""

import pytest

from tests.payloads import CURRY, PANCAKES, STEW

GUARDRAIL = (
    "I couldn't find a recipe in the collection that fits. "
    "Try rephrasing or loosening a diet filter."
)
ALLERGY_NOTE = (
    "Diet tags are auto-detected from ingredients — "
    "always double-check labels if you have an allergy."
)


@pytest.fixture
def seeded(client, auth_headers):
    """Alice's headers plus the ids of three indexed recipes."""
    h = auth_headers()
    ids = {
        body["title"]: client.post("/recipes", json=body, headers=h).json()["id"]
        for body in (CURRY, STEW, PANCAKES)
    }
    return h, ids


def test_ask_returns_answer_with_sources(client, seeded, fake_llm):
    h, ids = seeded
    curry_id = ids["Chickpea Curry"]
    fake_llm.chat_reply = lambda msgs: f"Try the chickpea curry [#{curry_id}]."
    r = client.post("/ask", json={"question": "chickpea curry with coconut milk"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["sources"][0]["recipe_id"] == curry_id
    assert body["sources"][0]["title"] == "Chickpea Curry"
    assert body["grounded"] is True
    assert "[#" in body["answer"]
    prompt = fake_llm.chat_calls[0][-1]["content"]
    assert "Chickpea Curry" in prompt


def test_ask_guardrail_off_topic(client, seeded, fake_llm):
    h, _ = seeded
    r = client.post("/ask", json={"question": "how do I change a car tire"}, headers=h)
    body = r.json()
    assert body["answer"] == GUARDRAIL
    assert body["sources"] == []
    assert body["grounded"] is False
    assert fake_llm.chat_calls == []


def test_hallucinated_citation_dropped(client, seeded, fake_llm):
    h, ids = seeded
    curry_id = ids["Chickpea Curry"]
    fake_llm.chat_reply = f"Make [#9999] or the curry [#{curry_id}]."
    r = client.post("/ask", json={"question": "chickpea curry with coconut milk"}, headers=h)
    assert [s["recipe_id"] for s in r.json()["sources"]] == [curry_id]


def test_uncited_answer_is_not_grounded(client, seeded, fake_llm):
    h, _ = seeded
    fake_llm.chat_reply = "Just make something nice."
    r = client.post("/ask", json={"question": "chickpea curry with coconut milk"}, headers=h)
    body = r.json()
    assert body["grounded"] is False
    assert len(body["sources"]) >= 1


def test_ask_ollama_down_503(client, seeded, fake_llm):
    h, _ = seeded
    fake_llm.down = True
    r = client.post("/ask", json={"question": "chickpea curry"}, headers=h)
    assert r.status_code == 503
    assert r.json()["detail"] == "The AI model isn't responding. Is Ollama running?"


def test_ask_empty_question_422(client, seeded):
    h, _ = seeded
    assert client.post("/ask", json={"question": "   "}, headers=h).status_code == 422


def test_ask_requires_auth(client):
    assert client.post("/ask", json={"question": "curry"}).status_code == 401


def test_allergy_note_when_tags(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = f"The curry [#{ids['Chickpea Curry']}] is vegan."
    r = client.post(
        "/ask", json={"question": "chickpea curry with coconut milk", "tags": ["vegan"]}, headers=h
    )
    assert r.json()["answer"].endswith(ALLERGY_NOTE)
