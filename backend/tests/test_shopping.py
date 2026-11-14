"""Tests for shopping list aggregation."""

from shopping import build_shopping_list, normalize_name


def test_merges_duplicates_across_recipes():
    result = build_shopping_list(
        [
            ("Soup", [{"name": "Onion", "measure": "1"}, {"name": "Carrots", "measure": "2"}]),
            ("Stew", [{"name": "onions", "measure": "2 chopped"}]),
        ],
        on_hand=[],
    )
    onion = next(i for i in result["items"] if i["name"] == "onion")
    assert onion["measures"] == ["1", "2 chopped"]
    assert onion["recipes"] == ["Soup", "Stew"]
    assert [i["name"] for i in result["items"]] == ["carrot", "onion"]


def test_on_hand_split_out():
    result = build_shopping_list(
        [("Pasta", [{"name": "Garlic", "measure": "2 cloves"}, {"name": "Pasta", "measure": ""}])],
        on_hand=["Garlic"],
    )
    assert "garlic" in result["have"]
    assert all(i["name"] != "garlic" for i in result["items"])


def test_normalize_keeps_double_s():
    assert normalize_name("  Swiss  Cheese ") == "swiss cheese"
    assert normalize_name("Cress") == "cress"
    assert normalize_name("tomatoes") == "tomato"
