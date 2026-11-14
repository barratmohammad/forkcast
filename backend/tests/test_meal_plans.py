"""Meal plan and shopping list endpoint tests."""

import json

import pytest

from tests.payloads import CURRY, PANCAKES, STEW


@pytest.fixture
def seeded(client, auth_headers):
    """Alice's headers plus the ids of three indexed recipes."""
    h = auth_headers()
    ids = {
        body["title"]: client.post("/recipes", json=body, headers=h).json()["id"]
        for body in (CURRY, STEW, PANCAKES)
    }
    return h, ids


def test_plan_uses_only_candidate_ids(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = json.dumps(
        {
            "items": [
                {"day": 1, "meal": "dinner", "recipe_id": ids["Chickpea Curry"]},
                {"day": 2, "meal": "dinner", "recipe_id": 9999},
            ],
            "notes": "Curry first while the coriander is fresh.",
        }
    )
    r = client.post("/meal-plans", json={"days": 2, "on_hand": ["chickpeas"]}, headers=h)
    assert r.status_code == 201
    plan = r.json()
    assert len(plan["items"]) == 2
    assert plan["items"][0]["recipe"]["id"] == ids["Chickpea Curry"]
    assert all(i["recipe"]["id"] in ids.values() for i in plan["items"])
    assert plan["notes"] == "Curry first while the coriander is fresh."
    assert plan["title"] == "2-day plan"


def test_plan_invalid_json_falls_back(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = "not json"
    r = client.post("/meal-plans", json={"days": 2, "meals_per_day": 2}, headers=h)
    assert r.status_code == 201
    items = r.json()["items"]
    assert len(items) == 4
    assert {(i["day"], i["meal"]) for i in items} == {
        (1, "lunch"),
        (1, "dinner"),
        (2, "lunch"),
        (2, "dinner"),
    }
    assert len(fake_llm.chat_calls) == 2


def test_plan_respects_diet_filter(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = "{}"
    r = client.post("/meal-plans", json={"days": 2, "tags": ["vegan"]}, headers=h)
    assert {i["recipe"]["id"] for i in r.json()["items"]} == {ids["Chickpea Curry"]}
    assert r.json()["title"] == "2-day plan (vegan)"


def test_plan_no_candidates_422(client, auth_headers):
    r = client.post("/meal-plans", json={"days": 1}, headers=auth_headers())
    assert r.status_code == 422
    assert r.json()["detail"] == "No recipes match those filters."


def test_list_get_delete_plan(client, seeded, fake_llm):
    h, _ = seeded
    fake_llm.chat_reply = "{}"
    pid = client.post("/meal-plans", json={"days": 1}, headers=h).json()["id"]
    plans = client.get("/meal-plans", headers=h).json()
    assert [(p["id"], p["item_count"]) for p in plans] == [(pid, 1)]
    assert client.get(f"/meal-plans/{pid}", headers=h).status_code == 200
    assert client.delete(f"/meal-plans/{pid}", headers=h).status_code == 204
    assert client.get(f"/meal-plans/{pid}", headers=h).status_code == 404


def test_shopping_list_for_plan(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = json.dumps(
        {
            "items": [
                {"day": 1, "meal": "dinner", "recipe_id": ids["Chickpea Curry"]},
                {"day": 2, "meal": "dinner", "recipe_id": ids["Beef Stew"]},
            ]
        }
    )
    pid = client.post("/meal-plans", json={"days": 2, "on_hand": ["garlic"]}, headers=h).json()[
        "id"
    ]
    sl = client.get(f"/meal-plans/{pid}/shopping-list", headers=h).json()
    assert sl["plan_id"] == pid
    assert "garlic" in sl["have"]
    names = [i["name"] for i in sl["items"]]
    assert "chickpea" in names and "beef" in names and "garlic" not in names


def test_other_users_plan_404(client, seeded, fake_llm, auth_headers):
    h, _ = seeded
    fake_llm.chat_reply = "{}"
    pid = client.post("/meal-plans", json={"days": 1}, headers=h).json()["id"]
    bob = auth_headers("bob")
    assert client.get(f"/meal-plans/{pid}", headers=bob).status_code == 404
    assert client.get(f"/meal-plans/{pid}/shopping-list", headers=bob).status_code == 404
    assert client.delete(f"/meal-plans/{pid}", headers=bob).status_code == 404


def test_plan_days_out_of_range_422(client, seeded):
    h, _ = seeded
    assert client.post("/meal-plans", json={"days": 9}, headers=h).status_code == 422


def test_deleting_recipe_removes_it_from_plans(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = json.dumps(
        {"items": [{"day": 1, "meal": "dinner", "recipe_id": ids["Fluffy Pancakes"]}]}
    )
    pid = client.post("/meal-plans", json={"days": 1}, headers=h).json()["id"]
    assert client.delete(f"/recipes/{ids['Fluffy Pancakes']}", headers=h).status_code == 204
    r = client.get(f"/meal-plans/{pid}", headers=h)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_plan_meal_names_are_case_insensitive(client, seeded, fake_llm):
    h, ids = seeded
    fake_llm.chat_reply = json.dumps(
        {"items": [{"day": 1, "meal": "Dinner ", "recipe_id": ids["Beef Stew"]}]}
    )
    r = client.post("/meal-plans", json={"days": 1}, headers=h)
    assert r.json()["items"][0]["recipe"]["id"] == ids["Beef Stew"]
