"""Tests for the frontend's API client error handling."""

import httpx
import pytest

from api_client import APIClient, APIError


def client_with(handler) -> APIClient:
    """APIClient whose HTTP calls go to `handler` instead of the network."""
    c = APIClient("http://backend:8000", token="t0k")
    c._http = httpx.Client(base_url=c.base_url, transport=httpx.MockTransport(handler))
    return c


def test_connect_error_message():
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(APIError) as err:
        client_with(boom).health()
    assert "Can't reach the ForkCast API at http://backend:8000" in err.value.message
    assert err.value.status is None


def test_timeout_message():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(APIError) as err:
        client_with(slow).ask("curry please", [])
    assert "timed out" in err.value.message


def test_401_status():
    c = client_with(lambda r: httpx.Response(401, json={"detail": "Could not validate"}))
    with pytest.raises(APIError) as err:
        c.me()
    assert err.value.status == 401


def test_422_names_field():
    body = {
        "detail": [{"loc": ["body", "password"], "msg": "String should have at least 8 characters"}]
    }
    c = client_with(lambda r: httpx.Response(422, json=body))
    with pytest.raises(APIError) as err:
        c.register("al", "short")
    assert err.value.message == "Password: String should have at least 8 characters"


def test_string_detail_passed_through():
    c = client_with(lambda r: httpx.Response(503, json={"detail": "Is Ollama running?"}))
    with pytest.raises(APIError) as err:
        c.ask("curry please", [])
    assert err.value.message == "Is Ollama running?"


def test_login_returns_token_and_sends_auth_header():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"})

    assert client_with(handler).login("alice", "supersecret") == "abc"
    assert seen["auth"] == "Bearer t0k"


def test_delete_returns_none_on_204():
    c = client_with(lambda r: httpx.Response(204))
    assert c.delete_recipe(5) is None
