"""Rule-based dietary tag detection from ingredient names.

These are heuristics, not guarantees: the UI always shows tags as editable and
the /ask endpoint appends an allergy disclaimer when diet filters are used.
"""

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
    "haddock",
    "mackerel",
    "sardine",
    "anchov",
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
    "stock cube",
    "chicken stock",
    "beef stock",
    "fish stock",
)
# Plant-based names that contain a meat keyword.
MEAT_EXCEPTIONS = ("vegetable stock", "veggie", "mushroom", "nutmeg", "coconut meat")

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


def _contains(name: str, keywords: tuple[str, ...], exceptions: tuple[str, ...]) -> bool:
    """True if `name` matches a keyword and is not covered by an exception phrase."""
    if any(exc in name for exc in exceptions):
        return False
    return any(kw in name for kw in keywords)


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
