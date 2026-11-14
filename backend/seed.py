"""Load the bundled TheMealDB recipes and keep the vector index in sync with SQL."""

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Recipe, User
from ollama_client import LLMUnavailable
from rag_pipeline import RecipeIndex
from routers.recipes import apply_tags

log = logging.getLogger(__name__)

SYSTEM_USERNAME = "forkcast"
SEED_PATH = Path(__file__).parent / "data" / "seed_recipes.json"


def ensure_system_user(db: Session) -> User:
    """Return the built-in owner of seed recipes, creating it if needed.

    Its password hash is "!", which is not a valid bcrypt hash, so it can never log in.
    """
    user = db.scalar(select(User).where(User.username == SYSTEM_USERNAME))
    if user is None:
        user = User(username=SYSTEM_USERNAME, hashed_password="!")
        db.add(user)
        db.commit()
    return user


def load_seed_recipes(db: Session, path: Path = SEED_PATH) -> int:
    """Insert seed recipes once. Returns how many were added (0 if already seeded)."""
    if db.scalar(select(Recipe.id).where(Recipe.source == "seed").limit(1)) is not None:
        return 0
    owner = ensure_system_user(db)
    rows = json.loads(path.read_text())
    for row in rows:
        recipe = Recipe(
            title=row["title"][:200],
            category=(row.get("category") or None),
            cuisine=(row.get("cuisine") or None),
            ingredients=row["ingredients"],
            instructions=row["instructions"],
            source="seed",
            owner=owner,
        )
        db.add(recipe)
        apply_tags(db, recipe, None)
    db.commit()
    log.info("Loaded %d seed recipes", len(rows))
    return len(rows)


def sync_index(db: Session, index: RecipeIndex) -> int:
    """Embed any recipes missing from the vector index. Never raises if Ollama is down."""
    missing_ids = set(db.scalars(select(Recipe.id))) - index.indexed_ids()
    if not missing_ids:
        return 0
    recipes = list(db.scalars(select(Recipe).where(Recipe.id.in_(missing_ids))))
    try:
        count = index.upsert(recipes)
    except LLMUnavailable:
        log.warning("Ollama unavailable; %d recipes not indexed yet", len(recipes))
        return 0
    log.info("Indexed %d recipes", count)
    return count
