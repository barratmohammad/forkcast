"""Recipe CRUD, tag and search endpoint tests."""

from tests.payloads import CURRY, PANCAKES, STEW


def test_recipe_crud_lifecycle(client, auth_headers):
    h = auth_headers()
    r = client.post("/recipes", json=CURRY, headers=h)
    assert r.status_code == 201
    recipe = r.json()
    assert "vegan" in recipe["tags"]
    assert recipe["owner_username"] == "alice"
    assert recipe["indexed"] is True
    rid = recipe["id"]

    assert client.get(f"/recipes/{rid}", headers=h).json()["title"] == "Chickpea Curry"

    r = client.put(f"/recipes/{rid}", json={"title": "Easy Chickpea Curry"}, headers=h)
    assert r.status_code == 200
    assert r.json()["title"] == "Easy Chickpea Curry"

    assert client.delete(f"/recipes/{rid}", headers=h).status_code == 204
    assert client.get(f"/recipes/{rid}", headers=h).status_code == 404


def test_recipes_require_auth(client):
    assert client.get("/recipes").status_code == 401
    assert client.post("/recipes", json=CURRY).status_code == 401


def test_cannot_modify_others_recipe(client, auth_headers):
    alice, bob = auth_headers("alice"), auth_headers("bob")
    rid = client.post("/recipes", json=CURRY, headers=alice).json()["id"]
    for r in (
        client.put(f"/recipes/{rid}", json={"title": "Mine now"}, headers=bob),
        client.delete(f"/recipes/{rid}", headers=bob),
    ):
        assert r.status_code == 403
        assert r.json()["detail"] == "You can only modify your own recipes"


def test_invalid_recipe_422(client, auth_headers):
    h = auth_headers()
    assert client.post("/recipes", json={**CURRY, "ingredients": []}, headers=h).status_code == 422
    assert client.post("/recipes", json={**CURRY, "title": "ab"}, headers=h).status_code == 422
    bad_tag = {**CURRY, "tags": ["keto"]}
    assert client.post("/recipes", json=bad_tag, headers=h).status_code == 422


def test_explicit_tags_override_detection(client, auth_headers):
    h = auth_headers()
    r = client.post("/recipes", json={**STEW, "tags": ["gluten-free"]}, headers=h)
    assert r.json()["tags"] == ["gluten-free"]


def test_list_filters_by_tag_and_mine(client, auth_headers):
    alice, bob = auth_headers("alice"), auth_headers("bob")
    client.post("/recipes", json=CURRY, headers=alice)
    client.post("/recipes", json=STEW, headers=alice)
    client.post("/recipes", json=PANCAKES, headers=bob)

    page = client.get("/recipes", params={"tag": "vegan"}, headers=alice).json()
    assert [r["title"] for r in page["items"]] == ["Chickpea Curry"]
    assert page["total"] == 1

    mine = client.get("/recipes", params={"mine": True}, headers=bob).json()
    assert [r["title"] for r in mine["items"]] == ["Fluffy Pancakes"]

    q = client.get("/recipes", params={"q": "carrots"}, headers=bob).json()
    assert [r["title"] for r in q["items"]] == ["Beef Stew"]

    both = client.get("/recipes", params={"tag": ["vegetarian", "dairy-free"]}, headers=bob)
    assert [r["title"] for r in both.json()["items"]] == ["Chickpea Curry"]


def test_tags_endpoint_counts(client, auth_headers):
    h = auth_headers()
    client.post("/recipes", json=CURRY, headers=h)
    tags = {t["name"]: t["recipe_count"] for t in client.get("/tags", headers=h).json()}
    assert tags["vegan"] == 1
    assert set(tags) == {"vegetarian", "vegan", "gluten-free", "dairy-free"}


def test_semantic_search_returns_hits(client, auth_headers):
    h = auth_headers()
    for body in (CURRY, STEW, PANCAKES):
        client.post("/recipes", json=body, headers=h)
    hits = client.post("/search", json={"query": "chickpea curry"}, headers=h).json()
    assert hits[0]["recipe"]["title"] == "Chickpea Curry"
    assert 0 <= hits[0]["score"] <= 1


def test_ingredient_edit_retags_and_reindexes(client, auth_headers):
    h = auth_headers()
    rid = client.post("/recipes", json=CURRY, headers=h).json()["id"]
    new_ings = CURRY["ingredients"] + [{"name": "chicken thighs", "measure": "500g"}]
    r = client.put(f"/recipes/{rid}", json={"ingredients": new_ings}, headers=h)
    assert "vegetarian" not in r.json()["tags"]
    hits = client.post(
        "/search", json={"query": "chickpea curry", "tags": ["vegetarian"]}, headers=h
    ).json()
    assert rid not in [hit["recipe"]["id"] for hit in hits]


def test_create_succeeds_when_ollama_down(client, auth_headers, fake_llm):
    h = auth_headers()
    fake_llm.down = True
    r = client.post("/recipes", json=CURRY, headers=h)
    assert r.status_code == 201
    assert r.json()["indexed"] is False


def test_search_503_when_ollama_down(client, auth_headers, fake_llm):
    h = auth_headers()
    client.post("/recipes", json=CURRY, headers=h)
    fake_llm.down = True
    r = client.post("/search", json={"query": "curry"}, headers=h)
    assert r.status_code == 503
    assert r.json()["detail"] == "The AI model isn't responding. Is Ollama running?"
