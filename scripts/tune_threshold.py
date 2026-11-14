"""Print the best-match cosine distance for on-topic vs off-topic questions.

Used to pick RAG_MAX_DISTANCE: it should sit between the two clusters.
Requires a running backend with the index built.

Usage:  python3 scripts/tune_threshold.py [API_URL] [USERNAME] [PASSWORD]
"""

import json
import sys
import urllib.parse
import urllib.request

ON_TOPIC = [
    "I have chickpeas and spinach, what can I make for dinner?",
    "something spicy with chicken",
    "an easy chocolate dessert",
    "vegan curry",
    "quick pasta for a weeknight",
    "how do I make pancakes",
    "a fish dish with lemon",
    "slow cooked beef stew",
    "something with leftover rice",
    "a light summer salad",
    "Japanese food",
    "what can I bake with apples",
]
OFF_TOPIC = [
    "how do I change a car tire?",
    "what is the capital of France",
    "write me a poem about the ocean",
    "how do I reset my password",
    "explain quantum computing",
    "who won the world cup",
    "best laptop for programming",
    "how to train a puppy",
]


def call(url: str, data: bytes, headers: dict) -> dict:
    """POST and decode JSON."""
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    """Log in, query /search with k=1 for each question, print distances."""
    api = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    user = sys.argv[2] if len(sys.argv) > 2 else "demo"
    password = sys.argv[3] if len(sys.argv) > 3 else "demopass123"
    form = urllib.parse.urlencode({"username": user, "password": password}).encode()
    token = call(f"{api}/auth/token", form, {})["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    for label, questions in (("ON ", ON_TOPIC), ("OFF", OFF_TOPIC)):
        distances = []
        for q in questions:
            hit = call(f"{api}/search", json.dumps({"query": q, "k": 1}).encode(), headers)[0]
            distance = round(1 - hit["score"], 3)
            distances.append(distance)
            print(f"{label} {distance:.3f}  {q!r:60} -> {hit['recipe']['title']}")
        print(f"{label} min={min(distances):.3f} max={max(distances):.3f}\n")


if __name__ == "__main__":
    main()
