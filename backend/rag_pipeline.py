"""Retrieval-augmented generation: the recipe vector index, Q&A and meal planning."""

import re
from functools import lru_cache

import chromadb
from sqlalchemy.orm import Session

from config import get_settings
from dietary import DIET_TAGS, tag_to_meta_key
from models import Recipe
from ollama_client import get_llm
from schemas import AskResponse, Source

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


@lru_cache
def get_index() -> RecipeIndex:
    """FastAPI dependency returning the process-wide persistent recipe index."""
    settings = get_settings()
    client = chromadb.PersistentClient(
        str(settings.chroma_dir), settings=chromadb.Settings(anonymized_telemetry=False)
    )
    return RecipeIndex(client, get_llm())
