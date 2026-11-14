"""Recipe CRUD, diet tags and semantic search endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from dietary import DIET_TAGS, detect_tags
from models import Recipe, Tag, User, recipe_tags
from ollama_client import LLMUnavailable
from rag_pipeline import RecipeIndex, get_index
from schemas import (
    RecipeCreate,
    RecipeOut,
    RecipePage,
    RecipeUpdate,
    SearchHit,
    SearchRequest,
    TagOut,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["recipes"], dependencies=[Depends(get_current_user)])

NOT_OWNER = "You can only modify your own recipes"


def ensure_tags(db: Session) -> dict[str, Tag]:
    """Make sure every diet tag row exists; return them keyed by name."""
    existing = {t.name: t for t in db.scalars(select(Tag))}
    missing = [name for name in DIET_TAGS if name not in existing]
    for name in missing:
        existing[name] = Tag(name=name)
        db.add(existing[name])
    if missing:
        db.flush()  # make new tags visible to the next lookup (autoflush is off)
    return existing


def apply_tags(db: Session, recipe: Recipe, explicit: list[str] | None) -> None:
    """Set a recipe's tags: the explicit list if given, otherwise auto-detected."""
    if explicit is None:
        explicit = detect_tags([i["name"] for i in recipe.ingredients])
    names = explicit
    tags = ensure_tags(db)
    recipe.tags = [tags[n] for n in sorted(set(names))]


def to_out(recipe: Recipe, indexed: bool = True) -> RecipeOut:
    """Convert an ORM recipe to its response schema."""
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        category=recipe.category,
        cuisine=recipe.cuisine,
        ingredients=recipe.ingredients,
        instructions=recipe.instructions,
        tags=recipe.tag_names,
        source=recipe.source,
        owner_id=recipe.owner_id,
        owner_username=recipe.owner_username,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
        indexed=indexed,
    )


def sync_vector(index: RecipeIndex, recipe: Recipe) -> bool:
    """Upsert a recipe into the vector index; False (not an error) if Ollama is down."""
    try:
        index.upsert([recipe])
        return True
    except LLMUnavailable:
        log.warning("Recipe %s saved but not indexed: Ollama unavailable", recipe.id)
        return False


def get_recipe_or_404(db: Session, recipe_id: int) -> Recipe:
    """Load a recipe by id or raise 404."""
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    return recipe


@router.get("/recipes", response_model=RecipePage)
def list_recipes(
    q: str | None = Query(default=None, max_length=100),
    tag: list[str] = Query(default=[]),
    cuisine: str | None = None,
    mine: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecipePage:
    """Browse recipes with keyword and diet filters (plain SQL, no AI)."""
    stmt = select(Recipe)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Recipe.title.ilike(pattern), cast(Recipe.ingredients, String).ilike(pattern))
        )
    for t in tag:
        stmt = stmt.where(Recipe.tags.any(Tag.name == t))
    if cuisine:
        stmt = stmt.where(Recipe.cuisine == cuisine)
    if mine:
        stmt = stmt.where(Recipe.owner_id == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Recipe.title).limit(limit).offset(offset))
    return RecipePage(items=[to_out(r) for r in rows], total=total)


@router.post("/recipes", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    body: RecipeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    index: RecipeIndex = Depends(get_index),
) -> RecipeOut:
    """Create a recipe, tag it, and add it to the vector index."""
    data = body.model_dump(exclude={"tags"})
    recipe = Recipe(**data, source="user", owner=user)
    db.add(recipe)
    apply_tags(db, recipe, body.tags)
    db.commit()
    db.refresh(recipe)
    return to_out(recipe, indexed=sync_vector(index, recipe))


@router.get("/recipes/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)) -> RecipeOut:
    """Fetch one recipe."""
    return to_out(get_recipe_or_404(db, recipe_id))


@router.put("/recipes/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int,
    body: RecipeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    index: RecipeIndex = Depends(get_index),
) -> RecipeOut:
    """Update fields of a recipe you own; re-tags if ingredients change and re-indexes."""
    recipe = get_recipe_or_404(db, recipe_id)
    if recipe.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_OWNER)
    changes = body.model_dump(exclude_unset=True, exclude={"tags"})
    for field, value in changes.items():
        if value is not None:
            setattr(recipe, field, value)
    if body.tags is not None:
        apply_tags(db, recipe, body.tags)
    elif "ingredients" in changes:
        apply_tags(db, recipe, None)
    db.commit()
    db.refresh(recipe)
    return to_out(recipe, indexed=sync_vector(index, recipe))


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    index: RecipeIndex = Depends(get_index),
) -> Response:
    """Delete a recipe you own and remove it from the vector index."""
    recipe = get_recipe_or_404(db, recipe_id)
    if recipe.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_OWNER)
    db.delete(recipe)
    db.commit()
    index.delete(recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)) -> list[TagOut]:
    """All diet tags with recipe counts."""
    ensure_tags(db)
    db.commit()
    rows = db.execute(
        select(Tag.id, Tag.name, func.count(recipe_tags.c.recipe_id))
        .outerjoin(recipe_tags, recipe_tags.c.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    return [TagOut(id=i, name=n, recipe_count=c) for i, n, c in rows]


@router.post("/search", response_model=list[SearchHit])
def semantic_search(
    body: SearchRequest,
    db: Session = Depends(get_db),
    index: RecipeIndex = Depends(get_index),
) -> list[SearchHit]:
    """Find recipes by meaning using vector similarity (no LLM answer generation)."""
    hits = index.search(body.query, body.tags, body.k)
    results = []
    for recipe_id, distance in hits:
        recipe = db.get(Recipe, recipe_id)
        if recipe is not None:
            results.append(SearchHit(recipe=to_out(recipe), score=round(1 - distance, 3)))
    return results


@router.post("/admin/reindex")
def reindex(db: Session = Depends(get_db), index: RecipeIndex = Depends(get_index)) -> dict:
    """Rebuild the vector index from the database (recovery tool)."""
    recipes = list(db.scalars(select(Recipe)))
    index.llm.embed(["ping"])  # raises LLMUnavailable (503) before anything is deleted
    index.reset()
    return {"indexed": index.upsert(recipes)}
