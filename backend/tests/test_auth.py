"""Authentication tests: register, login, protected routes."""


def test_register_login_me(client):
    r = client.post("/auth/register", json={"username": "alice", "password": "supersecret"})
    assert r.status_code == 201
    assert r.json()["username"] == "alice"
    assert "hashed_password" not in r.json()

    r = client.post("/auth/token", data={"username": "alice", "password": "supersecret"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_wrong_password_401(client):
    client.post("/auth/register", json={"username": "alice", "password": "supersecret"})
    r = client.post("/auth/token", data={"username": "alice", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect username or password"


def test_unknown_user_401(client):
    r = client.post("/auth/token", data={"username": "nobody", "password": "whatever1"})
    assert r.status_code == 401


def test_duplicate_username_409(client):
    body = {"username": "alice", "password": "supersecret"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409


def test_protected_route_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    r = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_short_password_422(client):
    r = client.post("/auth/register", json={"username": "alice", "password": "short"})
    assert r.status_code == 422


def test_bad_username_chars_422(client):
    r = client.post("/auth/register", json={"username": "bad name!", "password": "supersecret"})
    assert r.status_code == 422
