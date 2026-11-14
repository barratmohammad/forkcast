"""Tests for the My Recipes form: payload cleaning and diet re-tagging on edit."""

import math

import pandas as pd
from streamlit.testing.v1 import AppTest

from views.my_recipes import clean_rows


def test_clean_rows_drops_blank_names_and_nan_measures():
    rows = clean_rows(
        [
            {"name": "salt", "measure": float("nan")},
            {"name": None, "measure": None},
            {"name": "pepper", "measure": pd.NA},
            {"name": float("nan"), "measure": "1 tsp"},
            {"name": " flour ", "measure": " 200g "},
        ]
    )
    assert rows == [
        {"name": "salt", "measure": ""},
        {"name": "pepper", "measure": ""},
        {"name": "flour", "measure": "200g"},
    ]
    assert not any(isinstance(r["measure"], float) and math.isnan(r["measure"]) for r in rows)


def _edit_harness():
    """Render the My Recipes tab for an existing vegan recipe with a fake API."""
    import streamlit as st

    from views import my_recipes

    recipe = {
        "id": 7,
        "title": "Chickpea Curry",
        "category": None,
        "cuisine": "Indian",
        "ingredients": [{"name": "chickpeas", "measure": "1 can"}],
        "instructions": "Simmer the chickpeas in the sauce.",
        "tags": ["dairy-free", "gluten-free", "vegan", "vegetarian"],
        "owner_username": "alice",
    }

    class FakeAPI:
        def list_recipes(self, **_):
            return {"items": [recipe], "total": 1}

        def update_recipe(self, recipe_id, payload):
            st.session_state.sent = payload
            return {**recipe, **payload, "indexed": True}

    st.session_state.setdefault("my_recipe_choice", 7)
    my_recipes.render(FakeAPI(), [])


def test_editing_recipe_re_detects_tags_by_default():
    at = AppTest.from_function(_edit_harness).run()
    assert not at.exception
    auto = next(c for c in at.checkbox if c.label.startswith("Auto-detect"))
    assert auto.value is True
    next(b for b in at.button if b.label == "Save changes").click().run()
    assert at.session_state["sent"]["tags"] is None
