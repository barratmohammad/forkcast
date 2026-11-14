"""'My Recipes' tab: create, edit and delete your own recipes."""

import pandas as pd
import streamlit as st

from api_client import APIClient, APIError
from ui import handle_error, recipe_details

DIET_TAGS = ["vegetarian", "vegan", "gluten-free", "dairy-free"]
NEW = "➕ New recipe"


def _text(value) -> str:
    """Cell value as stripped text; empty for None/NaN/NA (pandas fills blank cells)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value).strip()


def clean_rows(records: list[dict]) -> list[dict]:
    """Ingredient editor rows → API ingredients, dropping rows with no name."""
    rows = [{"name": _text(r.get("name")), "measure": _text(r.get("measure"))} for r in records]
    return [r for r in rows if r["name"]]


def _recipe_form(api: APIClient, existing: dict | None) -> None:
    """Create/edit form. `existing` is None for a new recipe."""
    key = f"form_{existing['id'] if existing else 'new'}"
    ingredients = existing["ingredients"] if existing else [{"name": "", "measure": ""}]
    with st.form(key, clear_on_submit=existing is None):
        title = st.text_input("Title", value=existing["title"] if existing else "")
        c1, c2 = st.columns(2)
        category = c1.text_input(
            "Category", value=(existing or {}).get("category") or "", placeholder="e.g. Dessert"
        )
        cuisine = c2.text_input(
            "Cuisine", value=(existing or {}).get("cuisine") or "", placeholder="e.g. Italian"
        )
        st.markdown("**Ingredients** — add a row per ingredient")
        table = st.data_editor(
            pd.DataFrame(ingredients, columns=["name", "measure"]),
            num_rows="dynamic",
            width="stretch",
            column_config={
                "name": st.column_config.TextColumn("Ingredient"),
                "measure": st.column_config.TextColumn("Amount"),
            },
            key=f"{key}_ings",
        )
        instructions = st.text_area(
            "Instructions", value=existing["instructions"] if existing else "", height=180
        )
        auto = st.checkbox(
            "Auto-detect diet tags from ingredients",
            value=True,
            help="ForkCast checks ingredients for meat, fish, dairy, eggs, honey and gluten. "
            "Leave this on when editing so tags stay correct if ingredients change.",
        )
        manual = st.multiselect(
            "Diet tags (used when auto-detect is off)",
            DIET_TAGS,
            default=existing["tags"] if existing else [],
        )
        submitted = st.form_submit_button(
            "Save changes" if existing else "Create recipe", type="primary"
        )

    if not submitted:
        return
    rows = clean_rows(table.to_dict("records"))
    if len(title.strip()) < 3 or not rows or len(instructions.strip()) < 10:
        st.warning(
            "A recipe needs a title (3+ characters), at least one ingredient, "
            "and instructions (10+ characters)."
        )
        return
    payload = {
        "title": title.strip(),
        "category": category.strip() or None,
        "cuisine": cuisine.strip() or None,
        "ingredients": rows,
        "instructions": instructions.strip(),
        "tags": None if auto else manual,
    }
    try:
        with st.spinner("Saving and indexing for search…"):
            saved = (
                api.update_recipe(existing["id"], payload)
                if existing
                else api.create_recipe(payload)
            )
    except APIError as err:
        handle_error(err)
        return
    st.session_state.get("recipe_cache", {}).pop(saved["id"], None)
    st.session_state.my_recipe_choice = saved["id"]
    note = "" if saved.get("indexed", True) else " (AI search will pick it up once Ollama is back)"
    st.toast(f"Saved “{saved['title']}”{note}", icon="✅")
    st.rerun()


def render(api: APIClient, diet: list[str]) -> None:
    """Draw the My Recipes tab."""
    st.subheader("My recipes")
    try:
        mine = api.list_recipes(mine=True, limit=100)["items"]
    except APIError as err:
        handle_error(err)
        return

    options = {NEW: None} | {f"{r['title']} (#{r['id']})": r for r in mine}
    labels = list(options)
    chosen_id = st.session_state.get("my_recipe_choice")
    index = next(
        (i for i, lbl in enumerate(labels) if options[lbl] and options[lbl]["id"] == chosen_id), 0
    )
    label = st.selectbox("Pick a recipe to view or edit", labels, index=index)
    recipe = options[label]
    st.session_state.my_recipe_choice = recipe["id"] if recipe else None

    if recipe is None:
        st.caption("Your recipes are added to the AI search index as soon as you save them.")
        _recipe_form(api, None)
        return

    view, edit = st.tabs(["View", "Edit / delete"])
    with view:
        st.markdown(f"### {recipe['title']}")
        recipe_details(recipe)
    with edit:
        _recipe_form(api, recipe)
        st.divider()
        st.markdown(f"**Delete “{recipe['title']}”**")
        confirm = st.checkbox("Yes, permanently delete this recipe", key=f"del_{recipe['id']}")
        if st.button("Delete recipe", disabled=not confirm, type="secondary"):
            try:
                api.delete_recipe(recipe["id"])
            except APIError as err:
                handle_error(err)
                return
            st.session_state.my_recipe_choice = None
            st.toast("Recipe deleted", icon="🗑️")
            st.rerun()
