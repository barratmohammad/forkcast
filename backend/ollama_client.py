"""Thin HTTP client for the Ollama API (embeddings + chat)."""

from functools import lru_cache

import httpx

from config import get_settings

UNAVAILABLE_MESSAGE = "The AI model isn't responding. Is Ollama running?"


class LLMUnavailable(Exception):
    """Raised when Ollama can't be reached, times out, or returns an error."""


class OllamaClient:
    """Calls Ollama's /api/embed and /api/chat endpoints over HTTP."""

    def __init__(self, base_url: str, model: str, embed_model: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON to Ollama and return the decoded response, mapping failures."""
        try:
            resp = httpx.post(f"{self.base_url}{path}", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMUnavailable(UNAVAILABLE_MESSAGE) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        data = self._post("/api/embed", {"model": self.embed_model, "input": texts})
        return data["embeddings"]

    def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """Send a chat conversation and return the assistant's reply text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if json_mode:
            payload["format"] = "json"
        return self._post("/api/chat", payload)["message"]["content"]

    def ping(self) -> bool:
        """True if the Ollama server answers within a few seconds."""
        try:
            return httpx.get(f"{self.base_url}/api/tags", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False


@lru_cache
def get_llm() -> OllamaClient:
    """FastAPI dependency returning the shared Ollama client."""
    s = get_settings()
    return OllamaClient(s.ollama_base_url, s.ollama_model, s.ollama_embed_model, s.ollama_timeout)
