"""One-time script: download recipes from TheMealDB into backend/data/seed_recipes.json.

TheMealDB (https://www.themealdb.com) offers a free public test API key ("1") for
educational and development use. The app reads the saved JSON and never calls the API
at runtime.

Usage:  python3 scripts/fetch_mealdb.py
"""

import json
import string
import time
import urllib.request
from pathlib import Path

API = "https://www.themealdb.com/api/json/v1/1/search.php?f={letter}"
OUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "seed_recipes.json"


def fetch_letter(letter: str) -> list[dict]:
    """Return the raw meal objects whose name starts with `letter`."""
    req = urllib.request.Request(API.format(letter=letter), headers={"User-Agent": "forkcast"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("meals") or []


def convert(meal: dict) -> dict:
    """Map a TheMealDB meal object to ForkCast's seed format."""
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if name:
            measure = (meal.get(f"strMeasure{i}") or "").strip()
            ingredients.append({"name": name, "measure": measure})
    return {
        "title": meal["strMeal"].strip(),
        "category": (meal.get("strCategory") or "").strip(),
        "cuisine": (meal.get("strArea") or "").strip(),
        "ingredients": ingredients,
        "instructions": (meal.get("strInstructions") or "").strip(),
        "source_url": (meal.get("strSource") or "").strip(),
    }


def main() -> None:
    """Fetch every letter, dedupe by title, and write sorted JSON."""
    recipes: dict[str, dict] = {}
    for letter in string.ascii_lowercase:
        for meal in fetch_letter(letter):
            recipe = convert(meal)
            if recipe["ingredients"] and len(recipe["instructions"]) >= 10:
                recipes.setdefault(recipe["title"].lower(), recipe)
        time.sleep(0.2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = sorted(recipes.values(), key=lambda r: r["title"])
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote {len(data)} recipes to {OUT}")


if __name__ == "__main__":
    main()
