"""Retrieval-augmented generation: the recipe vector index, Q&A and meal planning."""

import json
import logging
import re
from functools import lru_cache

import chromadb
from sqlalchemy.orm import Session

from config import get_settings
from dietary import DIET_TAGS, tag_to_meta_key
from models import Recipe
from ollama_client import get_llm
from schemas import AskResponse, MealPlanRequest, Source

log = logging.getLogger(__name__)

DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
MAX_INSTRUCTION_CHARS = 800

GUARDRAIL_ANSWER = (
    "I couldn't find a recipe in the collection that fits. "
    "Try rephrasing or loosening a diet filter."
)
ALLERGY_NOTE = (
    "Diet tags are auto-detected from ingredients — "
    "always double-check labels if you have an allergy."
)
CITATION = re.compile(r"\[#(\d+)\]")

ASK_SYSTEM_PROMPT = """You are ForkCast, a friendly, practical chef assistant.
Answer the user's cooking question using ONLY the recipes provided below.
Rules:
- Recommend or discuss only the provided recipes. Never invent recipes or ingredients.
- Cite every recipe you mention with its id in square brackets, like [#12].
- If none of the provided recipes fit the question, say so plainly.
- Be concise: a short recommendation, then key ingredients or steps if helpful."""


def recipe_document(recipe: Recipe) -> str:
    """Text that gets embedded for a recipe: one chunk per recipe."""
    ingredients = ", ".join(
        f"{i['measure']} {i['name']}".strip() for i in recipe.ingredients if i.get("name")
    )
    parts = [
        recipe.title,
        f"Category: {recipe.category}" if recipe.category else "",
        f"Cuisine: {recipe.cuisine}" if recipe.cuisine else "",
        f"Diet: {', '.join(recipe.tag_names)}" if recipe.tags else "",
        f"Ingredients: {ingredients}",
        f"Instructions: {recipe.instructions[:MAX_INSTRUCTION_CHARS]}",
    ]
    return "\n".join(p for p in parts if p)


def recipe_metadata(recipe: Recipe) -> dict:
    """Filterable metadata stored next to each vector (diet flags, category, cuisine, owner)."""
    meta = {tag_to_meta_key(t): t in recipe.tag_names for t in DIET_TAGS}
    meta.update(
        category=recipe.category or "", cuisine=recipe.cuisine or "", owner_id=recipe.owner_id
    )
    return meta


def build_where(tags: list[str]) -> dict | None:
    """Chroma `where` filter requiring every given diet tag."""
    clauses = [{tag_to_meta_key(t): True} for t in tags]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


class RecipeIndex:
    """Wraps a Chroma collection of recipe embeddings."""

    BATCH = 32

    def __init__(self, chroma_client, llm, collection_name: str = "recipes"):
        self.client = chroma_client
        self.llm = llm
        self.collection_name = collection_name
        self.collection = self._open()

    def _open(self):
        """Get or create the cosine-distance collection."""
        return self.client.get_or_create_collection(
            self.collection_name, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, recipes: list[Recipe]) -> int:
        """Embed and store recipes (insert or replace). Returns how many were written."""
        for start in range(0, len(recipes), self.BATCH):
            batch = recipes[start : start + self.BATCH]
            docs = [recipe_document(r) for r in batch]
            vectors = self.llm.embed([DOC_PREFIX + d for d in docs])
            self.collection.upsert(
                ids=[str(r.id) for r in batch],
                embeddings=vectors,
                documents=docs,
                metadatas=[recipe_metadata(r) for r in batch],
            )
        return len(recipes)

    def delete(self, recipe_id: int) -> None:
        """Remove a recipe's vector (no-op if absent)."""
        self.collection.delete(ids=[str(recipe_id)])

    def count(self) -> int:
        """Number of indexed recipes."""
        return self.collection.count()

    def indexed_ids(self) -> set[int]:
        """IDs of all recipes currently in the index."""
        return {int(i) for i in self.collection.get(include=[])["ids"]}

    def search(self, query: str, tags: list[str], k: int) -> list[tuple[int, float]]:
        """Return up to k (recipe_id, cosine_distance) pairs, closest first."""
        total = self.count()
        if total == 0:
            return []
        vector = self.llm.embed([QUERY_PREFIX + query])[0]
        result = self.collection.query(
            query_embeddings=[vector], n_results=min(k, total), where=build_where(tags)
        )
        return [
            (int(rid), float(dist))
            for rid, dist in zip(result["ids"][0], result["distances"][0], strict=True)
        ]

    def reset(self) -> None:
        """Drop and recreate the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self._open()


def _context_block(recipe: Recipe) -> str:
    """Format one retrieved recipe for the LLM prompt."""
    tags = ", ".join(recipe.tag_names) or "none"
    ingredients = "; ".join(
        f"{i['measure']} {i['name']}".strip() for i in recipe.ingredients if i.get("name")
    )
    return (
        f"[#{recipe.id}] {recipe.title} (diet: {tags})\n"
        f"Ingredients: {ingredients}\n"
        f"Instructions: {recipe.instructions[:MAX_INSTRUCTION_CHARS]}"
    )


def answer_question(
    db: Session,
    index: RecipeIndex,
    llm,
    question: str,
    tags: list[str],
    top_k: int,
    max_distance: float,
) -> AskResponse:
    """Retrieve matching recipes, apply the relevance guardrail, and generate a cited answer."""
    hits = [(rid, d) for rid, d in index.search(question, tags, top_k) if d <= max_distance]
    recipes = [(db.get(Recipe, rid), d) for rid, d in hits]
    recipes = [(r, d) for r, d in recipes if r is not None]
    if not recipes:
        return AskResponse(answer=GUARDRAIL_ANSWER, sources=[], grounded=False)

    context = "\n\n".join(_context_block(r) for r, _ in recipes)
    filters = f"\nDiet filters: {', '.join(tags)}" if tags else ""
    messages = [
        {"role": "system", "content": ASK_SYSTEM_PROMPT},
        {"role": "user", "content": f"Recipes:\n{context}\n\nQuestion: {question}{filters}"},
    ]
    answer = llm.chat(messages).strip()

    by_id = {r.id: (r, d) for r, d in recipes}
    cited: list[int] = []
    for match in CITATION.findall(answer):
        rid = int(match)
        if rid in by_id and rid not in cited:
            cited.append(rid)
    grounded = bool(cited)
    chosen = cited if grounded else list(by_id)
    sources = [
        Source(recipe_id=rid, title=by_id[rid][0].title, score=round(1 - by_id[rid][1], 3))
        for rid in chosen
    ]
    if tags:
        answer = f"{answer}\n\n{ALLERGY_NOTE}"
    return AskResponse(answer=answer, sources=sources, grounded=grounded)


PLAN_SYSTEM_PROMPT = """You are ForkCast's meal planner.
Choose recipes ONLY from the candidate list, referring to them by id.
Fill every slot listed exactly once. Prefer recipes that use the ingredients the user
already has, avoid repeating a recipe unless there are too few candidates, and vary cuisines.
Respond with JSON only, in this exact shape:
{"items": [{"day": 1, "meal": "dinner", "recipe_id": 12}], "notes": "one or two sentences"}"""


def plan_slots(days: int, meals_per_day: int) -> list[tuple[int, str]]:
    """All (day, meal) slots for a plan, in display order."""
    meals = ["dinner"] if meals_per_day == 1 else ["lunch", "dinner"]
    return [(day, meal) for day in range(1, days + 1) for meal in meals]


def _parse_plan(raw: str) -> dict | None:
    """Parse the LLM's JSON plan; None if it isn't a JSON object."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def plan_meals(
    db: Session, index: RecipeIndex, llm, req: MealPlanRequest
) -> tuple[list[tuple[int, str, int]], str]:
    """Pick a recipe for every slot from retrieved candidates.

    Returns ([(day, meal, recipe_id)], notes). The LLM may only choose candidate ids;
    anything else is discarded and empty slots are filled with the best-ranked candidates.
    Raises ValueError if no recipe matches the filters.
    """
    parts = []
    if req.on_hand:
        parts.append("meals using " + ", ".join(req.on_hand))
    if req.notes:
        parts.append(req.notes)
    query = ". ".join(parts) or "easy dinner"
    ranked = [rid for rid, _ in index.search(query, req.tags, 20)]
    candidates = [r for r in (db.get(Recipe, rid) for rid in ranked) if r is not None]
    if not candidates:
        raise ValueError("No recipes match those filters.")
    candidate_ids = [r.id for r in candidates]
    slots = plan_slots(req.days, req.meals_per_day)

    lines = [
        f"[{r.id}] {r.title} ({', '.join(r.tag_names) or 'no diet tags'}): "
        + ", ".join(i["name"] for i in r.ingredients[:8])
        for r in candidates
    ]
    user_msg = (
        "Candidates:\n"
        + "\n".join(lines)
        + "\n\nSlots: "
        + ", ".join(f"day {d} {m}" for d, m in slots)
        + f"\nIngredients on hand: {', '.join(req.on_hand) or 'none'}"
        + f"\nDiet filters: {', '.join(req.tags) or 'none'}"
        + f"\nUser notes: {req.notes or 'none'}"
    )
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    data = None
    for _ in range(2):
        data = _parse_plan(llm.chat(messages, json_mode=True))
        if data is not None:
            break
        log.warning("Meal plan reply was not valid JSON; retrying")

    chosen: dict[tuple[int, str], int] = {}
    items = (data or {}).get("items", [])
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            slot = (int(item.get("day")), str(item.get("meal")))
            rid = int(item.get("recipe_id"))
        except (TypeError, ValueError):
            continue
        if slot in slots and slot not in chosen and rid in candidate_ids:
            chosen[slot] = rid

    used = set(chosen.values())
    fallback = [rid for rid in candidate_ids if rid not in used] or candidate_ids
    position = 0
    for slot in slots:
        if slot not in chosen:
            chosen[slot] = fallback[position % len(fallback)]
            position += 1

    notes = (data or {}).get("notes", "")
    notes = notes if isinstance(notes, str) else ""
    return [(d, m, chosen[(d, m)]) for d, m in slots], notes


@lru_cache
def get_index() -> RecipeIndex:
    """FastAPI dependency returning the process-wide persistent recipe index."""
    settings = get_settings()
    client = chromadb.PersistentClient(
        str(settings.chroma_dir), settings=chromadb.Settings(anonymized_telemetry=False)
    )
    return RecipeIndex(client, get_llm())
