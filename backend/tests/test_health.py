"""Health endpoint test."""


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "database", "vector_store", "ollama", "indexed_recipes"}
    assert body["database"] is True


def test_health_reports_dependencies(client):
    body = client.get("/health").json()
    assert body["ollama"] is True
    assert body["vector_store"] is True
    assert body["status"] == "ok"


def test_health_degraded_when_ollama_down(client, fake_llm):
    fake_llm.down = True
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ollama"] is False
    assert r.json()["status"] == "degraded"
