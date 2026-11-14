"""Application settings loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the backend. Values come from env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    storage_dir: Path = Path("./storage")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout: float = 90

    rag_top_k: int = 5
    rag_max_distance: float = 0.41

    seed_on_startup: bool = True

    @property
    def database_url(self) -> str:
        """SQLite URL for the main database file inside the storage directory."""
        return f"sqlite:///{self.storage_dir / 'forkcast.db'}"

    @property
    def chroma_dir(self) -> Path:
        """Directory where ChromaDB persists its vector index."""
        return self.storage_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance."""
    return Settings()
