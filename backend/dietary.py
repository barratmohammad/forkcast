"""Rule-based dietary tag detection from ingredient names.

Keywords match whole words (plus a plural "s"/"es"), so "mince" does not match
"minced garlic" and "bun" does not match "bunch".

These are heuristics, not guarantees: the UI always shows tags as editable and
the /ask endpoint appends an allergy disclaimer when diet filters are used.
"""

import re

DIET_TAGS: tuple[str, ...] = ("vegetarian", "vegan", "gluten-free", "dairy-free")

MEAT_AND_FISH = (
    "beef",
    "steak",
    "veal",
    "pork",
    "bacon",
    "ham",
    "prosciutto",
    "pancetta",
    "chorizo",
    "sausage",
    "salami",
    "pepperoni",
    "lamb",
    "mutton",
    "goat",
    "chicken",
    "turkey",
    "duck",
    "goose",
    "venison",
    "rabbit",
    "mince",
    "meat",
    "liver",
    "kidney",
    "oxtail",
    "gelatin",
    "gelatine",
    "lard",
    "suet",
    "dripping",
    "fish",
    "salmon",
    "tuna",
    "cod",
    "codfish",
    "haddock",
    "mackerel",
    "sardine",
    "anchovy",
    "anchovies",
    "trout",
    "tilapia",
    "halibut",
    "monkfish",
    "prawn",
    "shrimp",
    "crab",
    "lobster",
    "mussel",
    "clam",
    "oyster",
    "scallop",
    "squid",
    "octopus",
    "calamari",
    "worcestershire",
    "sea bass",
    "bass",
    "herring",
    "barramundi",
    "conch",
    "jamón",
    "jamon",
    "seafood",
    "bream",
    "snapper",
    "hake",
    "pollock",
    "kipper",
    "eel",
    "caviar",
    "meatball",
    "pork belly",
    "bouillon",
    "stock cube",
    "chicken stock",
    "beef stock",
    "fish stock",
)
# Plant-based names that contain a meat keyword.
MEAT_EXCEPTIONS = (
    "kidney bean",
    "goats cheese",
    "goat cheese",
    "goat's cheese",
    "vegetable bouillon",
    "vegetable stock",
    "veggie",
    "mushroom",
    "nutmeg",
    "coconut meat",
)

DAIRY = (
    "milk",
    "butter",
    "cheese",
    "cheddar",
    "parmesan",
    "parmigiano",
    "mozzarella",
    "feta",
    "ricotta",
    "mascarpone",
    "gruyere",
    "gruyère",
    "brie",
    "camembert",
    "paneer",
    "halloumi",
    "cream",
    "creme",
    "crème",
    "yogurt",
    "yoghurt",
    "ghee",
    "custard",
    "buttermilk",
)
DAIRY_EXCEPTIONS = (
    "coconut milk",
    "coconut cream",
    "almond milk",
    "soy milk",
    "soya milk",
    "oat milk",
    "rice milk",
    "peanut butter",
    "almond butter",
    "cashew butter",
    "nut butter",
    "cocoa butter",
    "butternut",
    "butter beans",
    "cream of tartar",
)

OTHER_ANIMAL = ("egg", "honey", "mayonnaise")
OTHER_ANIMAL_EXCEPTIONS = ("eggplant", "egg-free", "vegan mayo")

GLUTEN = (
    "flour",
    "bread",
    "pasta",
    "spaghetti",
    "linguine",
    "fettuccine",
    "tagliatelle",
    "penne",
    "macaroni",
    "lasagne",
    "lasagna",
    "noodle",
    "soy sauce",
    "barley",
    "couscous",
    "bulgur",
    "semolina",
    "breadcrumb",
    "breadcrumbs",
    "tortilla",
    "pastry",
    "beer",
    "rye",
    "wheat",
    "farro",
    "spelt",
    "biscuit",
    "cracker",
    "naan",
    "pitta",
    "pita",
    "bun",
    "brioche",
    "croissant",
    "ditalini",
    "orzo",
    "udon",
    "gnocchi",
    "seitan",
    "malt",
)
GLUTEN_EXCEPTIONS = (
    "rice flour",
    "almond flour",
    "corn flour",
    "cornflour",
    "coconut flour",
    "gluten-free",
    "gluten free",
    "rice noodle",
    "glass noodle",
    "corn tortilla",
    "buckwheat",
    "tamari",
    "rice vermicelli",
)


def _pattern(words: tuple[str, ...]) -> re.Pattern:
    """Regex matching any of `words` as a whole word, optionally pluralized."""
    alternatives = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})(?:e?s)?\b")


_PATTERNS: dict[tuple[str, ...], re.Pattern] = {}


def _contains(name: str, keywords: tuple[str, ...], exceptions: tuple[str, ...]) -> bool:
    """True if `name` matches a keyword and is not covered by an exception phrase."""
    for words in (keywords, exceptions):
        if words not in _PATTERNS:
            _PATTERNS[words] = _pattern(words)
    if _PATTERNS[exceptions].search(name):
        return False
    return bool(_PATTERNS[keywords].search(name))


def detect_tags(ingredient_names: list[str]) -> list[str]:
    """Return the sorted diet tags that every ingredient in the list satisfies."""
    names = [n.lower().strip() for n in ingredient_names]
    has_meat = any(_contains(n, MEAT_AND_FISH, MEAT_EXCEPTIONS) for n in names)
    has_dairy = any(_contains(n, DAIRY, DAIRY_EXCEPTIONS) for n in names)
    has_other_animal = any(_contains(n, OTHER_ANIMAL, OTHER_ANIMAL_EXCEPTIONS) for n in names)
    has_gluten = any(_contains(n, GLUTEN, GLUTEN_EXCEPTIONS) for n in names)

    tags = []
    if not has_meat:
        tags.append("vegetarian")
        if not has_dairy and not has_other_animal:
            tags.append("vegan")
    if not has_dairy:
        tags.append("dairy-free")
    if not has_gluten:
        tags.append("gluten-free")
    return sorted(tags)


def tag_to_meta_key(tag: str) -> str:
    """Convert a tag name to its ChromaDB metadata key (hyphens are not allowed in keys)."""
    return tag.replace("-", "_")
