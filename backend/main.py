"""ForkCast FastAPI application factory and health endpoint."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import get_settings
from database import Base, SessionLocal, engine, get_db
from ollama_client import LLMUnavailable, get_llm
from rag_pipeline import RecipeIndex, get_index
from routers import ask as ask_router
from routers import auth as auth_router
from routers import meal_plans as meal_plans_router
from routers import recipes as recipes_router
from schemas import Health
from seed import load_seed_recipes, sync_index

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _index_in_background() -> None:
    """Embed un-indexed recipes without blocking startup (300 embeddings take a while)."""
    with SessionLocal() as db:
        sync_index(db, get_index())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup: load seed recipes once, then index anything missing in the background."""
    if app.state.seed:
        with SessionLocal() as db:
            load_seed_recipes(db)
        threading.Thread(target=_index_in_background, daemon=True).start()
    yield


def create_app(seed: bool | None = None) -> FastAPI:
    """Build the FastAPI app. `seed=False` skips loading seed recipes (used by tests)."""
    Base.metadata.create_all(engine)
    app = FastAPI(
        title="ForkCast API",
        description="AI recipe assistant: grounded recipe Q&A, meal plans and shopping lists.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.seed = get_settings().seed_on_startup if seed is None else seed
    app.include_router(auth_router.router)
    app.include_router(recipes_router.router)
    app.include_router(ask_router.router)
    app.include_router(meal_plans_router.router)

    @app.exception_handler(LLMUnavailable)
    def llm_unavailable(_: Request, exc: LLMUnavailable) -> JSONResponse:
        """Turn Ollama outages into a friendly 503 instead of a 500."""
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
        )

    @app.get("/health", response_model=Health, tags=["health"])
    def health(
        db: Session = Depends(get_db),
        index: RecipeIndex = Depends(get_index),
        llm=Depends(get_llm),
    ) -> Health:
        """Report whether the database, vector store and Ollama are reachable. Always 200."""
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        try:
            indexed = index.count()
            vs_ok = True
        except Exception:
            indexed, vs_ok = 0, False
        ollama_ok = llm.ping()
        return Health(
            status="ok" if db_ok and vs_ok and ollama_ok else "degraded",
            database=db_ok,
            vector_store=vs_ok,
            ollama=ollama_ok,
            indexed_recipes=indexed,
        )

    return app


app = create_app()
