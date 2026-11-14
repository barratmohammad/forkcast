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
