"""'Meal Plan' tab: generate a plan from the collection and build a shopping list."""

import streamlit as st

from api_client import APIClient, APIError
from ui import handle_error, recipe_details


def _shopping_markdown(plan: dict, shopping: dict) -> str:
    """Shopping list as a downloadable Markdown checklist."""
    lines = [f"# Shopping list — {plan['title']}", ""]
    for item in shopping["items"]:
        amounts = f" ({', '.join(item['measures'])})" if item["measures"] else ""
        lines.append(f"- [ ] {item['name']}{amounts} — for {', '.join(item['recipes'])}")
    if shopping["have"]:
        lines += ["", "## Already have", *[f"- {name}" for name in shopping["have"]]]
    return "\n".join(lines) + "\n"


def _show_plan(api: APIClient, plan_id: int) -> None:
    """Render a saved plan, its shopping list and actions."""
    try:
        plan = api.get_plan(plan_id)
        shopping = api.shopping_list(plan_id)
    except APIError as err:
        if err.status == 404:
            st.session_state.current_plan_id = None
            st.warning("That meal plan no longer exists.")
            return
        handle_error(err)
        return

    st.markdown(f"### {plan['title']}")
    if plan["notes"]:
        st.info(plan["notes"], icon="🧑‍🍳")

    days = sorted({i["day"] for i in plan["items"]})
    cols = st.columns(min(len(days), 4) or 1)
    for n, day in enumerate(days):
        with cols[n % len(cols)]:
            st.markdown(f"**Day {day}**")
            for item in [i for i in plan["items"] if i["day"] == day]:
                with st.expander(f"{item['meal'].capitalize()}: {item['recipe']['title']}"):
                    recipe_details(item["recipe"])
    if not plan["items"]:
        st.caption("The recipes in this plan have been deleted.")

    st.markdown("#### 🛒 Shopping list")
    st.caption(
        f"{len(shopping['items'])} items to buy"
        + (f" · you already have: {', '.join(shopping['have'])}" if shopping["have"] else "")
    )
    left, right = st.columns(2)
    for n, item in enumerate(shopping["items"]):
        amounts = f" — {', '.join(item['measures'])}" if item["measures"] else ""
        (left if n % 2 == 0 else right).checkbox(
            f"{item['name']}{amounts}", key=f"shop_{plan_id}_{n}", help=", ".join(item["recipes"])
        )
    a, b = st.columns(2)
    a.download_button(
        "⬇️ Download shopping list (.md)",
        _shopping_markdown(plan, shopping),
        file_name=f"forkcast-shopping-list-{plan_id}.md",
        mime="text/markdown",
        width="stretch",
    )
    if b.button("🗑️ Delete this plan", width="stretch"):
        try:
            api.delete_plan(plan_id)
        except APIError as err:
            handle_error(err)
            return
        st.session_state.current_plan_id = None
        st.toast("Meal plan deleted", icon="🗑️")
        st.rerun()


def render(api: APIClient, diet: list[str]) -> None:
    """Draw the meal planning tab."""
    st.subheader("Meal planner")
    with st.form("plan_form"):
        c1, c2 = st.columns(2)
        days = c1.slider("How many days?", 1, 7, 3)
        meals = c2.radio("Meals per day", ["Dinner only", "Lunch + dinner"], horizontal=True)
        on_hand = st.text_input(
            "Ingredients you already have (comma-separated)",
            placeholder="chickpeas, spinach, rice",
        )
        notes = st.text_input("Anything else?", placeholder="quick weeknight meals, no mushrooms…")
        st.caption(f"Diet filters: **{', '.join(diet) or 'none'}** (set them in the sidebar)")
        go = st.form_submit_button("Plan my meals", type="primary")

    if go:
        items = [x.strip() for x in on_hand.split(",") if x.strip()][:20]
        payload = {
            "days": days,
            "meals_per_day": 2 if meals == "Lunch + dinner" else 1,
            "tags": diet,
            "on_hand": [x[:50] for x in items],
            "notes": notes.strip()[:300],
        }
        try:
            with st.spinner("Picking recipes from the collection… (this can take ~10 seconds)"):
                st.session_state.current_plan_id = api.create_plan(payload)["id"]
        except APIError as err:
            handle_error(err)

    try:
        plans = api.list_plans()
    except APIError as err:
        handle_error(err)
        return
    if plans:
        ids = [p["id"] for p in plans]
        labels = {p["id"]: f"{p['title']} · {p['created_at'][:10]} (#{p['id']})" for p in plans}
        current = st.session_state.get("current_plan_id")
        chosen = st.selectbox(
            "Your meal plans",
            ids,
            index=ids.index(current) if current in ids else 0,
            format_func=labels.get,
        )
        st.session_state.current_plan_id = chosen
        st.divider()
        _show_plan(api, chosen)
    else:
        st.caption("No meal plans yet — fill in the form above to make your first one.")
