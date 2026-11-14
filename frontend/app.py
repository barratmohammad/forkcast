"""ForkCast Streamlit frontend: login gate, sidebar, and the four main tabs."""

import streamlit as st

from api_client import DEFAULT_API_URL, APIClient, APIError
from ui import handle_error
from views import ask, browse, meal_plan, my_recipes

st.set_page_config(page_title="ForkCast", page_icon="🍴", layout="wide")

DIET_TAGS = ["vegetarian", "vegan", "gluten-free", "dairy-free"]


def api() -> APIClient:
    """API client carrying the current session's token."""
    return APIClient(DEFAULT_API_URL, token=st.session_state.get("token"))


@st.cache_data(ttl=15, show_spinner=False)
def health_status(base_url: str) -> dict | None:
    """Backend health, cached briefly so every rerun doesn't hit the API."""
    try:
        return APIClient(base_url, timeout=5).health()
    except APIError:
        return None


def login_screen() -> None:
    """Centered login / register screen."""
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title("🍴 ForkCast")
        st.markdown(
            "**Tell it what you've got and what you can't eat — "
            "it finds real recipes and plans your week.**"
        )
        if flash := st.session_state.pop("flash", None):
            st.warning(flash)
        if health_status(DEFAULT_API_URL) is None:
            st.error(f"Can't reach the ForkCast API at {DEFAULT_API_URL}. Is the backend running?")
        login_tab, register_tab = st.tabs(["Log in", "Create account"])
        with login_tab, st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                _authenticate(username, password, register=False)
        with register_tab, st.form("register"):
            username = st.text_input("Choose a username", help="3–50 letters, numbers, . _ -")
            password = st.text_input(
                "Choose a password", type="password", help="At least 8 characters"
            )
            if st.form_submit_button("Create account", type="primary", width="stretch"):
                _authenticate(username, password, register=True)


def _authenticate(username: str, password: str, register: bool) -> None:
    """Register (optionally) then log in, storing the token in the session."""
    if not username or not password:
        st.warning("Please enter a username and password.")
        return
    client = APIClient(DEFAULT_API_URL)
    try:
        if register:
            client.register(username.strip(), password)
        st.session_state.token = client.login(username.strip(), password)
        st.session_state.username = username.strip()
    except APIError as err:
        st.error(err.message, icon="⚠️")
        return
    st.rerun()


def sidebar(client: APIClient) -> list[str]:
    """Sidebar with user, service status, diet filters and stats. Returns active diet tags."""
    with st.sidebar:
        st.markdown("## 🍴 ForkCast")
        st.caption(f"Logged in as **{st.session_state.username}**")

        health = health_status(DEFAULT_API_URL)
        dot = lambda ok: "🟢" if ok else "🔴"  # noqa: E731
        if health:
            st.markdown(
                f"{dot(True)} API &nbsp; {dot(health['ollama'])} AI model &nbsp; "
                f"{dot(health['vector_store'])} Search index"
            )
            if not health["ollama"]:
                st.caption("Ollama isn't responding: chat, AI search and meal plans are paused.")
        else:
            st.markdown(f"{dot(False)} API unreachable")

        st.markdown("#### Diet filters")
        st.caption("Applied to chat, search and meal plans.")
        diet = [t for t in DIET_TAGS if st.checkbox(t.capitalize(), key=f"diet_{t}")]

        st.markdown("#### Stats")
        try:
            total = client.list_recipes(limit=1)["total"]
            mine = client.list_recipes(mine=True, limit=1)["total"]
            plans = len(client.list_plans())
        except APIError as err:
            handle_error(err)
        else:
            a, b = st.columns(2)
            a.metric("Recipes", total)
            b.metric("Mine", mine)
            a.metric("Meal plans", plans)
            if health:
                b.metric("Indexed", health["indexed_recipes"])

        st.divider()
        if st.button("Log out", width="stretch"):
            st.session_state.clear()
            st.rerun()
        st.caption("Recipes from TheMealDB · Answers by Ollama")
    return diet


def main() -> None:
    """Route between the login screen and the main app."""
    if not st.session_state.get("token"):
        login_screen()
        return
    client = api()
    diet = sidebar(client)
    tabs = st.tabs(["💬 Ask the Chef", "🔎 Browse", "📖 My Recipes", "🗓️ Meal Plan"])
    for tab, view in zip(tabs, (ask, browse, my_recipes, meal_plan), strict=True):
        with tab:
            view.render(client, diet)


main()
