"""Tests for the ChromaDB recipe index."""

import pytest

from models import Recipe, Tag, User


@pytest.fixture
def recipes(db_session):
    """Two recipes: a vegan chickpea curry and a beef stew."""
    user = User(username="chef", hashed_password="!")
    vegan = Tag(name="vegan")
    veg = Tag(name="vegetarian")
    curry = Recipe(
        title="Chickpea Curry",
        cuisine="Indian",
        ingredients=[
            {"name": "chickpeas", "measure": "1 can"},
            {"name": "curry powder", "measure": "2 tbsp"},
            {"name": "coconut milk", "measure": "400ml"},
        ],
        instructions="Fry the curry powder, add chickpeas and coconut milk, simmer.",
        owner=user,
        tags=[vegan, veg],
    )
    stew = Recipe(
        title="Beef Stew",
        ingredients=[{"name": "beef", "measure": "1kg"}, {"name": "carrots", "measure": "3"}],
        instructions="Brown the beef, add carrots and stock, simmer for two hours.",
        owner=user,
    )
    db_session.add_all([curry, stew])
    db_session.commit()
    return curry, stew


def test_search_finds_relevant_recipe(index, recipes):
    curry, stew = recipes
    assert index.upsert([curry, stew]) == 2
    hits = index.search("chickpea curry", [], 2)
    assert hits[0][0] == curry.id
    assert 0 <= hits[0][1] < hits[1][1]


def test_diet_filter_excludes(index, recipes):
    curry, stew = recipes
    index.upsert([curry, stew])
    ids = [rid for rid, _ in index.search("beef stew", ["vegetarian"], 5)]
    assert stew.id not in ids
    assert ids == [curry.id]


def test_multiple_tag_filter(index, recipes):
    curry, stew = recipes
    index.upsert([curry, stew])
    ids = [rid for rid, _ in index.search("dinner", ["vegan", "vegetarian"], 5)]
    assert ids == [curry.id]


def test_delete_removes(index, recipes):
    curry, stew = recipes
    index.upsert([curry, stew])
    index.delete(stew.id)
    assert index.count() == 1
    assert index.indexed_ids() == {curry.id}


def test_upsert_is_idempotent(index, recipes):
    curry, _ = recipes
    index.upsert([curry])
    index.upsert([curry])
    assert index.count() == 1
