"""Deterministic shopping list aggregation for meal plans (no LLM involved)."""

import re


def normalize_name(name: str) -> str:
    """Lowercase, collapse whitespace and naively singularize an ingredient name."""
    n = re.sub(r"\s+", " ", name.strip().lower())
    if len(n) <= 3 or n.endswith(("ss", "us")):
        return n
    if n.endswith("oes"):
        return n[:-2]
    if n.endswith("ies"):
        return n[:-3] + "y"
    if n.endswith("s"):
        return n[:-1]
    return n


def build_shopping_list(recipes: list[tuple[str, list[dict]]], on_hand: list[str]) -> dict:
    """Group ingredients from (recipe_title, ingredients) pairs into a shopping list.

    Returns {"items": [{"name", "measures", "recipes"}], "have": [names]} sorted by name;
    ingredients matching an on-hand item go to "have" instead of "items".
    """
    have_names = {normalize_name(x) for x in on_hand if x.strip()}
    grouped: dict[str, dict] = {}
    have: set[str] = set()
    for title, ingredients in recipes:
        for ing in ingredients:
            key = normalize_name(ing.get("name", ""))
            if not key:
                continue
            if key in have_names:
                have.add(key)
                continue
            entry = grouped.setdefault(key, {"name": key, "measures": [], "recipes": []})
            measure = (ing.get("measure") or "").strip()
            if measure:
                entry["measures"].append(measure)
            if title not in entry["recipes"]:
                entry["recipes"].append(title)
    return {"items": [grouped[k] for k in sorted(grouped)], "have": sorted(have)}
