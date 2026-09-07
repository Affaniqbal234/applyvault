import os
from pathlib import Path
import subprocess
import sqlite3
import sys

import asyncpg
import pytest


BACKEND = Path(__file__).resolve().parents[1] / "backend"


def run_backend(url, *arguments):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = url
    environment["JWT_SECRET"] = "disposable-postgres-test-secret"
    return subprocess.run(
        [sys.executable, *arguments], cwd=BACKEND, env=environment,
        capture_output=True, text=True, timeout=60,
    )


def alembic(url, *arguments):
    result = run_backend(url, "-m", "alembic", *arguments)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


async def insert_records(connection):
    user_id = await connection.fetchval(
        "INSERT INTO users (email, hashed_password, created_at) "
        "VALUES ('existing@example.com', 'test-hash', CURRENT_TIMESTAMP) RETURNING id"
    )
    application_id = await connection.fetchval(
        "INSERT INTO applications "
        "(user_id, company, role, status, date_applied, notes, created_at, updated_at) "
        "VALUES ($1, 'Example', 'Intern', 'Applied', DATE '2025-06-01', "
        "'Keep this note', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id",
        user_id,
    )
    return user_id, application_id


async def test_upgrade_matches_models_and_repeated_upgrade_preserves_rows(postgres_url):
    alembic(postgres_url, "upgrade", "head")
    alembic(postgres_url, "check")
    connection = await asyncpg.connect(postgres_url)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0001"
        user_id, application_id = await insert_records(connection)
        before = await connection.fetchrow("SELECT * FROM applications WHERE id = $1", application_id)
        alembic(postgres_url, "upgrade", "head")
        assert await connection.fetchrow(
            "SELECT * FROM applications WHERE id = $1", application_id
        ) == before
        assert await connection.fetchval("SELECT id FROM users") == user_id
    finally:
        await connection.close()


async def test_initial_migration_downgrade_and_reupgrade(postgres_url):
    alembic(postgres_url, "upgrade", "head")
    alembic(postgres_url, "downgrade", "base")
    connection = await asyncpg.connect(postgres_url)
    try:
        assert await connection.fetchval("SELECT to_regclass('public.users')") is None
        assert await connection.fetchval("SELECT to_regclass('public.applications')") is None
    finally:
        await connection.close()
    alembic(postgres_url, "upgrade", "head")
    alembic(postgres_url, "check")


async def test_migration_command_ignores_inherited_application_database(postgres_url, tmp_path, monkeypatch):
    sentinel = tmp_path / "application.db"
    with sqlite3.connect(sentinel) as connection:
        connection.execute("CREATE TABLE sentinel (marker TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('keep me')")
    contents = sentinel.read_bytes()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{sentinel.as_posix()}")
    monkeypatch.setenv("PGHOST", "invalid.example")
    monkeypatch.setenv("PGPORT", "1")
    alembic(postgres_url, "upgrade", "head")
    assert sentinel.read_bytes() == contents
    connection = await asyncpg.connect(postgres_url)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0001"
    finally:
        await connection.close()


async def test_postgres_enforces_unique_foreign_key_nullability_and_lengths(postgres_url):
    alembic(postgres_url, "upgrade", "head")
    connection = await asyncpg.connect(postgres_url)
    try:
        user_id, application_id = await insert_records(connection)
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute(
                "INSERT INTO users (email, hashed_password, created_at) "
                "VALUES ('existing@example.com', 'other-hash', CURRENT_TIMESTAMP)"
            )
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await connection.execute("UPDATE applications SET user_id = 2147483647")
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await connection.execute("DELETE FROM users WHERE id = $1", user_id)
        for table, fields in {
            "users": ["email", "hashed_password", "created_at"],
            "applications": ["user_id", "company", "role", "status", "date_applied", "created_at", "updated_at"],
        }.items():
            for field in fields:
                with pytest.raises(asyncpg.NotNullViolationError):
                    await connection.execute(f"UPDATE {table} SET {field} = NULL")
        for table, field, maximum in [
            ("users", "email", 255), ("users", "hashed_password", 255),
            ("applications", "company", 255), ("applications", "role", 255),
            ("applications", "status", 50), ("applications", "url", 2048),
        ]:
            await connection.execute(f"UPDATE {table} SET {field} = $1", "a" * maximum)
            with pytest.raises(asyncpg.StringDataRightTruncationError):
                await connection.execute(f"UPDATE {table} SET {field} = $1", "a" * (maximum + 1))
        await connection.execute("UPDATE applications SET notes = NULL, url = NULL")
        row = await connection.fetchrow("SELECT * FROM applications WHERE id = $1", application_id)
        assert row["notes"] is None and row["url"] is None
        assert row["user_id"] == user_id
    finally:
        await connection.close()


async def test_existing_schema_backup_restore_and_adoption(
    postgres_url, rehearsal_url, postgres_cli, tmp_path,
):
    legacy = run_backend(postgres_url, "-c", """
import asyncio
from database import Base, engine
import models
async def create_legacy_schema():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
asyncio.run(create_legacy_schema())
""")
    assert legacy.returncode == 0, legacy.stdout + legacy.stderr
    connection = await asyncpg.connect(postgres_url)
    try:
        await insert_records(connection)
        users = await connection.fetch("SELECT * FROM users ORDER BY id")
        applications = await connection.fetch("SELECT * FROM applications ORDER BY id")
        backup = tmp_path / "before-alembic.dump"
        postgres_cli("pg_dump", "--dbname", postgres_url, "--format=custom", "--file", str(backup))
        postgres_cli(
            "pg_restore", "--dbname", rehearsal_url, "--no-owner", "--no-privileges",
            "--exit-on-error", str(backup),
        )
        # An existing schema must not be treated as an empty database.
        rejected = run_backend(rehearsal_url, "-m", "alembic", "upgrade", "head")
        assert rejected.returncode != 0
        alembic(rehearsal_url, "stamp", "0001")
        alembic(rehearsal_url, "check")
        alembic(rehearsal_url, "upgrade", "head")
        restored = await asyncpg.connect(rehearsal_url)
        try:
            assert await restored.fetch("SELECT * FROM users ORDER BY id") == users
            assert await restored.fetch("SELECT * FROM applications ORDER BY id") == applications
            assert await restored.fetchval(
                "INSERT INTO users (email, hashed_password, created_at) "
                "VALUES ('next@example.com', 'hash', CURRENT_TIMESTAMP) RETURNING id"
            ) > users[0]["id"]
        finally:
            await restored.close()
        assert await connection.fetchval("SELECT to_regclass('public.alembic_version')") is None
        alembic(postgres_url, "stamp", "0001")
        alembic(postgres_url, "check")
        alembic(postgres_url, "upgrade", "head")
        assert await connection.fetch("SELECT * FROM users ORDER BY id") == users
        assert await connection.fetch("SELECT * FROM applications ORDER BY id") == applications
        assert await connection.fetchval(
            "INSERT INTO users (email, hashed_password, created_at) "
            "VALUES ('next@example.com', 'hash', CURRENT_TIMESTAMP) RETURNING id"
        ) > users[0]["id"]
    finally:
        await connection.close()


async def test_schema_drift_is_reported_on_an_adoption_copy(postgres_url):
    alembic(postgres_url, "upgrade", "head")
    connection = await asyncpg.connect(postgres_url)
    try:
        await connection.execute("ALTER TABLE applications ALTER COLUMN company TYPE VARCHAR(100)")
    finally:
        await connection.close()
    result = run_backend(postgres_url, "-m", "alembic", "check")
    assert result.returncode != 0
    assert "company" in result.stdout + result.stderr


async def test_startup_does_not_create_tables_and_api_works_after_upgrade(postgres_url):
    startup = run_backend(postgres_url, "-c", """
import asyncio
from main import app
async def start():
    async with app.router.lifespan_context(app):
        pass
asyncio.run(start())
""")
    assert startup.returncode == 0, startup.stdout + startup.stderr
    connection = await asyncpg.connect(postgres_url)
    try:
        assert await connection.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        ) == 0
    finally:
        await connection.close()
    alembic(postgres_url, "upgrade", "head")
    flow = run_backend(postgres_url, "-c", """
import asyncio
from httpx import ASGITransport, AsyncClient
from main import app
async def flow():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            credentials = {'email': 'postgres@example.com', 'password': 'password123'}
            assert (await client.post('/register', json=credentials)).status_code == 201
            assert (await client.post('/register', json=credentials)).status_code == 409
            login = await client.post('/login', json=credentials)
            assert login.status_code == 200
            client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
            assert (await client.get('/me')).json() == {'email': credentials['email']}
            created = await client.post('/applications', json={
                'company': 'Example', 'role': 'Intern', 'date_applied': '2025-06-01', 'notes': 'clear me'
            })
            assert created.status_code == 201
            path = '/applications/' + str(created.json()['id'])
            updated = await client.patch(path, json={'notes': None, 'status': 'Interview'})
            assert updated.status_code == 200
            assert updated.json()['notes'] is None
            assert updated.json()['status'] == 'Interview'
            assert (await client.get('/applications/stats')).json()['total'] == 1
            assert (await client.delete(path)).status_code == 204
            assert (await client.get('/applications')).json() == []
asyncio.run(flow())
""")
    assert flow.returncode == 0, flow.stdout + flow.stderr
