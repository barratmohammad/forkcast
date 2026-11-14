"""Health endpoint test."""


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "database", "vector_store", "ollama", "indexed_recipes"}
    assert body["database"] is True
