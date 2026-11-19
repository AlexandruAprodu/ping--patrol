from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import select

from services.users.constants import REFRESH_TOKEN_COOKIE_NAME


pytestmark = pytest.mark.asyncio(loop_scope="session")
BASE = "/api/v1/auth"


def user_payload():
    key = uuid4().hex[:14]
    return {
        "email": f"{key}@example.com",
        "username": f"user_{key}",
        "password": "SafePassword123!",
    }


async def register(client, payload=None):
    data = payload or user_payload()
    response = await client.post(f"{BASE}/register/", json=data)
    assert response.status_code == 201, response.text
    return data, response.json()


async def login(client, username, password):
    return await client.post(
        f"{BASE}/login",
        data={"username": username, "password": password},
    )


async def test_register_login_and_me_with_real_postgres(users_client):
    users = users_client
    data, created = await register(users)

    assert UUID(created["id"])
    assert created["email"] == data["email"]
    assert created["username"] == data["username"]
    assert "password" not in created
    assert "password_hash" not in created
    assert created["created_at"]

    from services.users.db import SessionLocal
    from services.users.models import User
    from services.users.password import verify_password

    async with SessionLocal() as session:
        persisted = await session.get(User, UUID(created["id"]))
        assert persisted is not None
        assert persisted.password_hash != data["password"]
        assert verify_password(data["password"], persisted.password_hash)

    response = await login(users, data["username"], data["password"])
    assert response.status_code == 200, response.text
    token_response = response.json()
    assert token_response["token_type"] == "bearer"
    assert token_response["access_token"]
    assert REFRESH_TOKEN_COOKIE_NAME in users.cookies

    from services.users.security import JWT_SECRET
    from services.users.constants import JWT_ALGORITHM
    decoded = jwt.decode(token_response["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert decoded["sub"] == created["id"]
    assert decoded["type"] == "access_token"

    me_response = await users.get(
        f"{BASE}/me/",
        headers={"Authorization": f"Bearer {token_response['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["id"] == created["id"]

    by_email = await login(users, data["email"], data["password"])
    assert by_email.status_code == 200
    assert by_email.json()["access_token"]


async def test_register_validation_and_duplicate_email_username(users_client):
    users = users_client
    payload, _ = await register(users)

    invalid = {**user_payload(), "email": "not-an-email"}
    assert (await users.post(f"{BASE}/register/", json=invalid)).status_code == 422

    invalid = {**user_payload(), "username": "ab"}
    assert (await users.post(f"{BASE}/register/", json=invalid)).status_code == 422

    invalid = {**user_payload(), "password": "short"}
    assert (await users.post(f"{BASE}/register/", json=invalid)).status_code == 422

    duplicate_email = {**user_payload(), "email": payload["email"]}
    response = await users.post(f"{BASE}/register/", json=duplicate_email)
    assert response.status_code == 409
    assert response.json()["detail"] == "Email already exists."

    duplicate_username = {**user_payload(), "username": payload["username"]}
    response = await users.post(f"{BASE}/register/", json=duplicate_username)
    assert response.status_code == 409
    assert response.json()["detail"] == "Username already exists."


async def test_login_rejects_unknown_user_or_bad_password(users_client):
    users = users_client
    payload, _ = await register(users)

    for identifier, password in (
        (payload["username"], "IncorrectPassword123!"),
        ("unknown_user", payload["password"]),
    ):
        response = await login(users, identifier, password)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials."


async def test_me_requires_valid_access_token(users_client):
    users = users_client
    assert (await users.get(f"{BASE}/me/")).status_code == 401
    assert (
        await users.get(f"{BASE}/me/", headers={"Authorization": "Bearer malformed"})
    ).status_code == 401


async def test_refresh_rotates_token_and_rejects_reuse(users_client):
    users = users_client
    payload, _ = await register(users)
    result = await login(users, payload["username"], payload["password"])
    assert result.status_code == 200
    old_refresh = users.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    assert old_refresh

    response = await users.post(f"{BASE}/refresh/")
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    new_refresh = users.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    assert new_refresh and new_refresh != old_refresh

    # Reusing a rotated refresh token must fail even though it was once valid.
    response = await users.post(
        f"{BASE}/refresh/",
        cookies={REFRESH_TOKEN_COOKIE_NAME: old_refresh},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token."


async def test_refresh_without_cookie_and_logout_revocation(users_client):
    users = users_client
    assert (await users.post(f"{BASE}/refresh/")).status_code == 401

    payload, _ = await register(users)
    result = await login(users, payload["email"], payload["password"])
    assert result.status_code == 200
    refresh = users.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    assert refresh

    response = await users.post(f"{BASE}/logout/")
    assert response.status_code == 200
    assert response.json() == {"detail": "Logged out."}
    assert users.cookies.get(REFRESH_TOKEN_COOKIE_NAME) is None

    response = await users.post(
        f"{BASE}/refresh/",
        cookies={REFRESH_TOKEN_COOKIE_NAME: refresh},
    )
    assert response.status_code == 401
