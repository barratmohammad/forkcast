"""Shared Streamlit helpers: error handling and recipe rendering."""

import streamlit as st

from api_client import APIClient, APIError

TAG_COLORS = {
    "vegetarian": "green",
    "vegan": "violet",
    "gluten-free": "orange",
    "dairy-free": "blue",
}


def handle_error(err: APIError) -> None:
    """Show an API error. An expired session sends the user back to the login screen."""
    if err.status == 401 and st.session_state.get("token"):
        for key in ("token", "username", "messages", "current_plan_id"):
            st.session_state.pop(key, None)
        st.session_state.flash = "Your session expired — please log in again."
        st.rerun()
    st.error(err.message, icon="⚠️")


def tag_badges(tags: list[str]) -> str:
    """Markdown colored badges for diet tags."""
    return " ".join(f":{TAG_COLORS.get(t, 'gray')}-background[{t}]" for t in tags) or "—"


def recipe_details(recipe: dict) -> None:
    """Render a recipe's tags, meta, ingredients and instructions."""
    meta = " · ".join(x for x in (recipe.get("cuisine"), recipe.get("category")) if x)
    st.markdown(
        f"{tag_badges(recipe['tags'])}  \n*{meta or 'Uncategorized'}* · "
        f"by **{recipe['owner_username']}**"
    )
    left, right = st.columns([1, 2])
    with left:
        st.markdown("**Ingredients**")
        st.markdown(
            "\n".join(
                f"- {i['measure']} {i['name']}".replace("-  ", "- ") for i in recipe["ingredients"]
            )
        )
    with right:
        st.markdown("**Instructions**")
        st.markdown(recipe["instructions"])


def cached_recipe(api: APIClient, recipe_id: int) -> dict | None:
    """Fetch a recipe once per session (used for chat sources)."""
    cache = st.session_state.setdefault("recipe_cache", {})
    if recipe_id not in cache:
        try:
            cache[recipe_id] = api.get_recipe(recipe_id)
        except APIError as err:
            if err.status == 404:
                return None
            handle_error(err)
            return None
    return cache[recipe_id]
