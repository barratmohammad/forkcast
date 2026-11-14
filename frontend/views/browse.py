"""'Browse' tab: keyword and semantic recipe search."""

import streamlit as st

from api_client import APIClient, APIError
from ui import handle_error, recipe_details

PAGE_SIZE = 20


def render(api: APIClient, diet: list[str]) -> None:
    """Draw the browse/search tab."""
    st.subheader("Browse recipes")
    c1, c2 = st.columns([3, 2])
    query = c1.text_input("Search", placeholder="e.g. lentils, 'cozy winter soup', Thai…")
    mode = c2.radio(
        "Search by",
        ["Keyword", "Meaning (AI)"],
        horizontal=True,
        help="Keyword matches titles and ingredients. Meaning uses vector search, "
        "so 'cozy winter soup' finds stews even if those words aren't in the recipe.",
    )
    if diet:
        st.caption(f"Diet filters: **{', '.join(diet)}** (change them in the sidebar)")

    try:
        if mode == "Meaning (AI)":
            if len(query.strip()) < 2:
                st.info("Type what you're in the mood for to search by meaning.", icon="✨")
                return
            with st.spinner("Searching by meaning…"):
                hits = api.search(query.strip(), diet, k=10)
            if not hits:
                st.warning("No recipes match those filters.")
            for hit in hits:
                r = hit["recipe"]
                with st.expander(f"**{r['title']}** · match {hit['score']:.0%}"):
                    recipe_details(r)
            return

        if st.session_state.get("browse_key") != (query, tuple(diet)):
            st.session_state.browse_key = (query, tuple(diet))
            st.session_state.browse_page = 0
        page = st.session_state.browse_page
        data = api.list_recipes(q=query.strip(), tag=diet, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    except APIError as err:
        handle_error(err)
        return

    total = data["total"]
    st.caption(f"{total} recipe{'s' if total != 1 else ''} found")
    if not data["items"]:
        st.warning("Nothing matched. Try fewer words or remove a diet filter.")
    for r in data["items"]:
        with st.expander(f"**{r['title']}** · {r.get('cuisine') or ''} {r.get('category') or ''}"):
            recipe_details(r)

    pages = max(1, -(-total // PAGE_SIZE))
    if pages > 1:
        prev, info, nxt = st.columns([1, 2, 1])
        if prev.button("← Previous", disabled=page == 0, width="stretch"):
            st.session_state.browse_page = page - 1
            st.rerun()
        info.markdown(
            f"<div style='text-align:center'>Page {page + 1} of {pages}</div>",
            unsafe_allow_html=True,
        )
        if nxt.button("Next →", disabled=page >= pages - 1, width="stretch"):
            st.session_state.browse_page = page + 1
            st.rerun()
