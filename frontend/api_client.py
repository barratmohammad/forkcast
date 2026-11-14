"""HTTP client for the ForkCast API. Every failure becomes an APIError with a readable message."""

import os

import httpx

DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8000")


class APIError(Exception):
    """A user-presentable API failure. `status` is None when the server was unreachable."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def _error_message(resp: httpx.Response) -> str:
    """Pull a human-readable message out of an error response."""
    try:
        detail = resp.json().get("detail")
    except ValueError:
        return f"Unexpected error from the API (HTTP {resp.status_code})."
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        field = str(first.get("loc", ["", "input"])[-1]).replace("_", " ").capitalize()
        return f"{field}: {first.get('msg', 'invalid value')}"
    return f"Unexpected error from the API (HTTP {resp.status_code})."


class APIClient:
    """Thin wrapper over the ForkCast REST API."""

    def __init__(self, base_url: str = DEFAULT_API_URL, token: str | None = None, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def _request(self, method: str, path: str, **kwargs):
        """Send a request; return decoded JSON (None for 204) or raise APIError."""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            resp = self._http.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException:
            raise APIError(
                "The request timed out — the AI model may still be loading. Try again."
            ) from None
        except httpx.HTTPError:
            raise APIError(
                f"Can't reach the ForkCast API at {self.base_url}. Is the backend running?"
            ) from None
        if resp.status_code >= 400:
            raise APIError(_error_message(resp), resp.status_code)
        return None if resp.status_code == 204 else resp.json()

    # ----- auth -----
    def register(self, username: str, password: str) -> dict:
        """Create an account."""
        return self._request(
            "POST", "/auth/register", json={"username": username, "password": password}
        )

    def login(self, username: str, password: str) -> str:
        """Log in and return the access token."""
        data = self._request(
            "POST", "/auth/token", data={"username": username, "password": password}
        )
        return data["access_token"]

    def me(self) -> dict:
        """The logged-in user."""
        return self._request("GET", "/auth/me")

    def health(self) -> dict:
        """Backend and dependency status."""
        return self._request("GET", "/health")

    # ----- recipes -----
    def list_recipes(self, **filters) -> dict:
        """Browse recipes. Filters: q, tag (list), cuisine, mine, limit, offset."""
        params = {k: v for k, v in filters.items() if v not in (None, "", [], False)}
        return self._request("GET", "/recipes", params=params)

    def get_recipe(self, recipe_id: int) -> dict:
        """One recipe."""
        return self._request("GET", f"/recipes/{recipe_id}")

    def create_recipe(self, payload: dict) -> dict:
        """Create a recipe."""
        return self._request("POST", "/recipes", json=payload)

    def update_recipe(self, recipe_id: int, payload: dict) -> dict:
        """Update a recipe you own."""
        return self._request("PUT", f"/recipes/{recipe_id}", json=payload)

    def delete_recipe(self, recipe_id: int) -> None:
        """Delete a recipe you own."""
        return self._request("DELETE", f"/recipes/{recipe_id}")

    def tags(self) -> list[dict]:
        """Diet tags with recipe counts."""
        return self._request("GET", "/tags")

    def search(self, query: str, tags: list[str], k: int = 10) -> list[dict]:
        """Semantic recipe search."""
        return self._request("POST", "/search", json={"query": query, "tags": tags, "k": k})

    # ----- AI -----
    def ask(self, question: str, tags: list[str]) -> dict:
        """Ask the chef a question."""
        return self._request("POST", "/ask", json={"question": question, "tags": tags})

    # ----- meal plans -----
    def create_plan(self, payload: dict) -> dict:
        """Generate a meal plan."""
        return self._request("POST", "/meal-plans", json=payload)

    def list_plans(self) -> list[dict]:
        """Your meal plans."""
        return self._request("GET", "/meal-plans")

    def get_plan(self, plan_id: int) -> dict:
        """One meal plan."""
        return self._request("GET", f"/meal-plans/{plan_id}")

    def delete_plan(self, plan_id: int) -> None:
        """Delete a meal plan."""
        return self._request("DELETE", f"/meal-plans/{plan_id}")

    def shopping_list(self, plan_id: int) -> dict:
        """Shopping list for a plan."""
        return self._request("GET", f"/meal-plans/{plan_id}/shopping-list")
