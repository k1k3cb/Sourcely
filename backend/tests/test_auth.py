import pytest


@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "supersecret"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert "id" in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_returns_409(client):
    payload = {"email": "bob@example.com", "password": "supersecret"}
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "supersecret"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success_sets_cookie(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "supersecret"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "supersecret"},
    )
    assert resp.status_code == 200
    assert "token" in resp.cookies
    assert resp.cookies["token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "supersecret"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "wrongpass1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "supersecret"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_email_is_case_insensitive(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "Eve@Example.com", "password": "supersecret"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": "supersecret"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_me_without_cookie_returns_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_cookie_returns_user(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "frank@example.com", "password": "supersecret"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "frank@example.com", "password": "supersecret"},
    )
    assert login.status_code == 200
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "frank@example.com"


@pytest.mark.asyncio
async def test_me_with_bearer_token(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "gina@example.com", "password": "supersecret"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "gina@example.com", "password": "supersecret"},
    )
    token = login.cookies.get("token")
    assert token
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "gina@example.com"


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(client):
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_cookie(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "harry@example.com", "password": "supersecret"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "harry@example.com", "password": "supersecret"},
    )
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    set_cookie = resp.headers.get("set-cookie", "")
    assert "token=" in set_cookie.lower()


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
