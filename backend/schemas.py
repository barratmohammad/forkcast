"""Pydantic request/response schemas for every endpoint."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------- auth ----------


class UserCreate(BaseModel):
    """Registration payload."""

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    """Public view of a user (never includes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class Token(BaseModel):
    """JWT returned by the login endpoint."""

    access_token: str
    token_type: str = "bearer"


# ---------- health ----------


class Health(BaseModel):
    """Status of the backend and each dependency."""

    status: Literal["ok", "degraded"]
    database: bool
    vector_store: bool
    ollama: bool
    indexed_recipes: int


# ---------- recipes ----------

DietTag = Literal["vegetarian", "vegan", "gluten-free", "dairy-free"]


class Ingredient(BaseModel):
    """One ingredient line, e.g. {"name": "chickpeas", "measure": "1 can"}."""

    name: str = Field(min_length=1, max_length=100)
    measure: str = Field(default="", max_length=60)


class RecipeCreate(BaseModel):
    """Payload for creating a recipe. Omit `tags` to auto-detect them from ingredients."""

    title: str = Field(min_length=3, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    cuisine: str | None = Field(default=None, max_length=50)
    ingredients: list[Ingredient] = Field(min_length=1, max_length=50)
    instructions: str = Field(min_length=10, max_length=10000)
    tags: list[DietTag] | None = None


class RecipeUpdate(BaseModel):
    """Partial update; only fields that are sent are changed."""

    title: str | None = Field(default=None, min_length=3, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    cuisine: str | None = Field(default=None, max_length=50)
    ingredients: list[Ingredient] | None = Field(default=None, min_length=1, max_length=50)
    instructions: str | None = Field(default=None, min_length=10, max_length=10000)
    tags: list[DietTag] | None = None


class RecipeOut(BaseModel):
    """A recipe as returned by the API."""

    id: int
    title: str
    category: str | None
    cuisine: str | None
    ingredients: list[Ingredient]
    instructions: str
    tags: list[str]
    source: str
    owner_id: int
    owner_username: str
    created_at: datetime
    updated_at: datetime
    indexed: bool = True


class RecipePage(BaseModel):
    """A page of recipes plus the total number matching the filters."""

    items: list[RecipeOut]
    total: int


class TagOut(BaseModel):
    """A diet tag with the number of recipes carrying it."""

    id: int
    name: str
    recipe_count: int


class SearchRequest(BaseModel):
    """Semantic search query with optional diet filters."""

    query: str = Field(min_length=2, max_length=300)
    tags: list[DietTag] = []
    k: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    """A search result: the recipe and its similarity score (0–1, higher is closer)."""

    recipe: RecipeOut
    score: float
