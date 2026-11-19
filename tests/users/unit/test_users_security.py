from uuid import uuid4

import jwt

from services.users.constants import JWT_ALGORITHM
from services.users.password import hash_password, verify_password
from services.users.security import (
    JWT_SECRET,
    create_access_token,
    create_refresh_token,
    hash_token,
)


def test_password_hash_is_not_plaintext_and_verifies():
    hashed = hash_password("MyStrongPassword123!")
    assert hashed != "MyStrongPassword123!"
    assert verify_password("MyStrongPassword123!", hashed)
    assert not verify_password("WrongPassword123!", hashed)


def test_access_token_contains_signed_user_identity_and_expiry():
    user_id = uuid4()
    token = create_access_token(user_id)
    claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

    assert claims["sub"] == str(user_id)
    assert claims["type"] == "access_token"
    assert claims["exp"] > claims["iat"]


def test_refresh_token_hash_is_stable_and_does_not_store_plaintext():
    token = create_refresh_token()
    assert token
    hashed = hash_token(token)
    assert hashed != token
    assert len(hashed) == 64
    assert hash_token(token) == hashed
    assert hash_token(create_refresh_token()) != hashed
