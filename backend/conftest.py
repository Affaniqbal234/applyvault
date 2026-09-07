import os
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

_application_modules = {"database", "main", "backend.database", "backend.main"}
_loaded_application_modules = _application_modules.intersection(sys.modules)
if _loaded_application_modules:
    loaded_modules = ", ".join(sorted(_loaded_application_modules))
    raise RuntimeError(
        "Tests require a fresh Python process so the database can be isolated. "
        f"Already imported: {loaded_modules}"
    )

# Tests must never inherit the database used by the application. Each pytest
# process owns a unique temporary database that can be safely created and dropped.
_test_database_directory = tempfile.TemporaryDirectory(prefix="applyvault-tests-")
TEST_DATABASE_PATH = Path(_test_database_directory.name) / "applyvault.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DATABASE_PATH.as_posix()}"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest"

from httpx import ASGITransport, AsyncClient

from database import DATABASE_URL, Base, SessionLocal, engine, get_db
from main import app

if DATABASE_URL != TEST_DATABASE_URL:
    raise RuntimeError("The test database engine was not configured with the test-owned URL")


async def override_get_db():
    async with SessionLocal() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_database_directory():
    yield
    _test_database_directory.cleanup()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client):
    credentials = {"email": "test@example.com", "password": "password123"}
    register_response = await client.post("/register", json=credentials)
    assert register_response.status_code == 201

    login_response = await client.post("/login", json=credentials)
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
