"""'Ask the Chef' tab: chat grounded in the recipe collection."""

import streamlit as st

from api_client import APIClient, APIError
from ui import cached_recipe, handle_error, recipe_details

EXAMPLES = [
    "I have chickpeas, spinach and rice — what can I make tonight?",
    "Something spicy with chicken for a weeknight",
    "An easy dessert with apples",
]


def _render_sources(api: APIClient, message: dict, key_prefix: str) -> None:
    """Show the recipes an answer was grounded in."""
    if not message.get("sources"):
        return
    if not message.get("grounded"):
        st.caption("⚠️ The answer didn't cite specific recipes — these were the closest matches.")
    st.caption("Sources")
    for src in message["sources"]:
        label = f"#{src['recipe_id']} · {src['title']} · match {src['score']:.0%}"
        with st.expander(label):
            recipe = cached_recipe(api, src["recipe_id"])
            if recipe:
                recipe_details(recipe)
            else:
                st.write("This recipe is no longer available.")


def render(api: APIClient, diet: list[str]) -> None:
    """Draw the chat tab."""
    messages = st.session_state.setdefault("messages", [])
    top = st.columns([4, 1])
    top[0].subheader("Ask the Chef")
    if top[1].button("Clear chat", disabled=not messages, width="stretch"):
        st.session_state.messages = []
        st.rerun()
    st.caption(
        "Answers come only from ForkCast's recipe collection and cite their sources. "
        + (f"Diet filters on: **{', '.join(diet)}**." if diet else "No diet filters set.")
    )

    if not messages:
        st.markdown("**Try one of these:**")
        cols = st.columns(len(EXAMPLES))
        for col, example in zip(cols, EXAMPLES, strict=True):
            if col.button(example, width="stretch"):
                st.session_state.pending_question = example
                st.rerun()

    for idx, msg in enumerate(messages):
        with st.chat_message(msg["role"], avatar="🧑‍🍳" if msg["role"] == "assistant" else None):
            if msg.get("guardrail"):
                st.info(msg["content"], icon="🔎")
            else:
                st.markdown(msg["content"])
            _render_sources(api, msg, f"m{idx}")

    question = st.chat_input("Ask about recipes, ingredients, or what to cook…")
    question = question or st.session_state.pop("pending_question", None)
    if not question:
        return
    if len(question.strip()) < 3:
        st.warning("Please type a slightly longer question.")
        return

    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🧑‍🍳"):
        with st.spinner("Searching the recipe collection and asking the chef…"):
            try:
                result = api.ask(question, diet)
            except APIError as err:
                messages.pop()
                handle_error(err)
                return
    messages.append(
        {
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
            "grounded": result["grounded"],
            "guardrail": not result["sources"],
        }
    )
    st.rerun()
