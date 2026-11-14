"""ForkCast FastAPI application factory and health endpoint."""

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from routers import auth as auth_router
from schemas import Health


def create_app(seed: bool | None = None) -> FastAPI:
    """Build the FastAPI app. `seed=False` skips loading seed recipes (used by tests)."""
    Base.metadata.create_all(engine)
    app = FastAPI(
        title="ForkCast API",
        description="AI recipe assistant: grounded recipe Q&A, meal plans and shopping lists.",
        version="1.0.0",
    )
    app.include_router(auth_router.router)

    @app.get("/health", response_model=Health, tags=["health"])
    def health(db: Session = Depends(get_db)) -> Health:
        """Report whether the database, vector store and Ollama are reachable."""
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return Health(
            status="ok" if db_ok else "degraded",
            database=db_ok,
            vector_store=False,
            ollama=False,
            indexed_recipes=0,
        )

    return app


app = create_app()
