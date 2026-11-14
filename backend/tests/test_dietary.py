"""Tests for ingredient-based dietary tag detection."""

from dietary import detect_tags, tag_to_meta_key


def test_fish_sauce_not_vegetarian():
    tags = detect_tags(["rice noodles", "fish sauce", "lime"])
    assert "vegetarian" not in tags
    assert "gluten-free" in tags


def test_butter_not_vegan_or_dairy_free():
    assert detect_tags(["flour", "butter", "sugar"]) == ["vegetarian"]


def test_soy_sauce_not_gluten_free():
    assert detect_tags(["tofu", "soy sauce"]) == ["dairy-free", "vegan", "vegetarian"]


def test_coconut_milk_is_dairy_free():
    assert detect_tags(["chickpeas", "coconut milk", "rice"]) == [
        "dairy-free",
        "gluten-free",
        "vegan",
        "vegetarian",
    ]


def test_eggs_vegetarian_not_vegan():
    assert detect_tags(["eggs", "spinach"]) == ["dairy-free", "gluten-free", "vegetarian"]


def test_meat_detected_case_insensitively():
    assert "vegetarian" not in detect_tags(["Chicken Thighs", "Rice"])


def test_meta_key():
    assert tag_to_meta_key("gluten-free") == "gluten_free"
    assert tag_to_meta_key("vegan") == "vegan"


def test_whole_word_matching_avoids_false_meat():
    assert "vegetarian" in detect_tags(["minced garlic", "kidney beans", "goats cheese"])


def test_whole_word_matching_avoids_false_gluten():
    assert "gluten-free" in detect_tags(["bunch of coriander", "rice"])


def test_more_fish_detected():
    for fish in ("Sea Bass Fillets", "Herring", "barramundi", "jamón ibérico", "Conchs"):
        assert "vegetarian" not in detect_tags([fish]), fish
