"""Test doubles: a deterministic stand-in for the Ollama client."""

import hashlib
import math
import re

from ollama_client import LLMUnavailable

_PREFIX = re.compile(r"^search_(document|query):\s*")
DIM = 512


class FakeLLM:
    """Bag-of-words hash embeddings + canned chat replies. Never touches the network."""

    def __init__(self):
        self.down = False
        self.chat_reply = "No recipe matched."
        self.chat_calls: list[list[dict]] = []

    def _check(self):
        if self.down:
            raise LLMUnavailable("The AI model isn't responding. Is Ollama running?")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed each text as a normalized hashed bag of (singularized) words."""
        self._check()
        vectors = []
        for text in texts:
            vec = [0.0] * DIM
            for word in re.findall(r"[a-z]+", _PREFIX.sub("", text.lower())):
                word = word[:-1] if len(word) > 3 and word.endswith("s") else word
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """Record the call and return `chat_reply` (a string or a callable of messages)."""
        self._check()
        self.chat_calls.append(messages)
        return self.chat_reply(messages) if callable(self.chat_reply) else self.chat_reply

    def ping(self) -> bool:
        """Report availability."""
        return not self.down
