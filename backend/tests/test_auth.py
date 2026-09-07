import asyncio
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import ALGORITHM, JWT_SECRET
from database import SessionLocal
from models import User
from routers import auth as auth_router


CREDENTIALS = {"email": "auth@example.com", "password": "password123"}


@pytest.mark.parametrize("password", ["a" * 72, "é" * 36, "😀" * 18])
async def test_password_byte_boundary(client, password):
    credentials = {**CREDENTIALS, "password": password}
    assert (await client.post("/register", json=credentials)).status_code == 201
    assert (await client.post("/login", json=credentials)).status_code == 200

    for email in [CREDENTIALS["email"], "unknown@example.com"]:
        for endpoint in ["/register", "/login"]:
            response = await client.post(
                endpoint, json={"email": email, "password": password + "a"},
            )
            assert response.status_code == 422, (endpoint, email)
            error = response.json()["detail"][0]
            assert error["loc"] == ["body", "password"]
            assert "72 UTF-8 bytes" in error["msg"]


async def test_password_whitespace_is_preserved(client):
    credentials = {**CREDENTIALS, "password": " password123 "}
    assert (await client.post("/register", json=credentials)).status_code == 201
    assert (await client.post("/login", json=credentials)).status_code == 200
    assert (await client.post("/login", json=CREDENTIALS)).status_code == 401


async def test_invalid_credentials_have_consistent_response(client):
    assert (await client.post("/register", json=CREDENTIALS)).status_code == 201
    for credentials in [
        {**CREDENTIALS, "password": "wrong-password"},
        {**CREDENTIALS, "email": "unknown@example.com"},
    ]:
        response = await client.post("/login", json=credentials)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}
        assert response.headers["www-authenticate"] == "Bearer"


async def test_password_operations_run_off_the_event_loop(client, monkeypatch):
    event_loop_thread = threading.get_ident()
    calls = []

    def check_thread(name, operation):
        def checked(*args):
            assert threading.get_ident() != event_loop_thread
            calls.append(name)
            return operation(*args)
        return checked

    for name in ["hash_password", "verify_password"]:
        monkeypatch.setattr(
            auth_router, name, check_thread(name, getattr(auth_router, name)),
        )

    assert (await client.post("/register", json=CREDENTIALS)).status_code == 201
    assert (await client.post("/login", json=CREDENTIALS)).status_code == 200
    assert calls == ["hash_password", "verify_password"]


async def test_concurrent_registration_returns_one_conflict(client, monkeypatch):
    original_hash = auth_router.hash_password
    original_rollback = AsyncSession.rollback
    both_requests_checked_email = threading.Barrier(2)
    rollbacks = []
    event_loop_thread = threading.get_ident()

    def synchronized_hash(password):
        assert threading.get_ident() != event_loop_thread
        # Both requests must pass the email check before either can insert.
        both_requests_checked_email.wait(timeout=10)
        return original_hash(password)

    async def record_rollback(session):
        rollbacks.append(session)
        await original_rollback(session)

    monkeypatch.setattr(auth_router, "hash_password", synchronized_hash)
    monkeypatch.setattr(AsyncSession, "rollback", record_rollback)

    responses = await asyncio.gather(
        client.post("/register", json=CREDENTIALS),
        client.post("/register", json=CREDENTIALS),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json() == {"detail": "Email already registered"}
    assert len(rollbacks) == 1
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
    assert (await client.post("/login", json=CREDENTIALS)).status_code == 200


async def test_unrelated_integrity_error_is_not_reported_as_duplicate(client, monkeypatch):
    failure = IntegrityError("INSERT", {}, sqlite3.IntegrityError("other constraint"))
    original_rollback = AsyncSession.rollback
    rollbacks = []

    async def fail_commit(session):
        raise failure

    async def record_rollback(session):
        rollbacks.append(session)
        await original_rollback(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    monkeypatch.setattr(AsyncSession, "rollback", record_rollback)
    with pytest.raises(IntegrityError) as caught:
        await client.post("/register", json=CREDENTIALS)
    assert caught.value is failure
    assert len(rollbacks) == 1


async def test_expired_token_is_rejected(auth_client):
    valid_token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(valid_token, JWT_SECRET, algorithms=[ALGORITHM])
    payload["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    response = await auth_client.get(
        "/applications", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Token has expired"}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_invalid_tokens_are_rejected_without_server_errors(auth_client):
    valid_token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    payload = jwt.decode(valid_token, JWT_SECRET, algorithms=[ALGORITHM])
    tokens = {
        "malformed JWT": "not-a-jwt",
        "wrong signature": jwt.encode(payload, "wrong-secret", algorithm=ALGORITHM),
        "wrong algorithm": jwt.encode(payload, JWT_SECRET, algorithm="HS384"),
        "missing expiry": jwt.encode({"sub": payload["sub"]}, JWT_SECRET, algorithm=ALGORITHM),
        "missing subject": jwt.encode({"exp": payload["exp"]}, JWT_SECRET, algorithm=ALGORITHM),
    }
    for subject in [None, 1, "", "not-a-user-id", "1.0", "0", "-1", "2147483648", "9" * 100, "١", "999"]:
        tokens[f"subject {subject!r}"] = jwt.encode(
            {**payload, "sub": subject}, JWT_SECRET, algorithm=ALGORITHM,
        )
    for expiry in [None, "invalid", [], {}, float("inf")]:
        tokens[f"expiry {expiry!r}"] = jwt.encode(
            {**payload, "exp": expiry}, JWT_SECRET, algorithm=ALGORITHM,
        )

    for case, token in tokens.items():
        response = await auth_client.get(
            "/applications", headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401, case
        assert response.json() == {"detail": "Invalid token"}, case
        assert response.headers["www-authenticate"] == "Bearer", case

    assert (await auth_client.get("/applications")).status_code == 200


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer"])
async def test_missing_bearer_token_is_rejected(client, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    response = await client.get("/applications", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
