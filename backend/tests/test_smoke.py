import os
import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_smoke.db")
os.environ.setdefault("JWT_SECRET", "test-secret-for-smoke")

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database import Base, get_db
from main import app

test_engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def db_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client):
    await client.post("/register", json={"email": "test@example.com", "password": "password123"})
    res = await client.post("/login", json={"email": "test@example.com", "password": "password123"})
    token = res.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.mark.asyncio
async def test_register(client):
    res = await client.post("/register", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 201


@pytest.mark.asyncio
async def test_duplicate_register(client):
    await client.post("/register", json={"email": "a@b.com", "password": "password123"})
    res = await client.post("/register", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_login(client):
    await client.post("/register", json={"email": "a@b.com", "password": "password123"})
    res = await client.post("/login", json={"email": "a@b.com", "password": "password123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_wrong_password(client):
    await client.post("/register", json={"email": "a@b.com", "password": "password123"})
    res = await client.post("/login", json={"email": "a@b.com", "password": "wrongpass"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_application(auth_client):
    res = await auth_client.post("/applications", json={
        "company": "Stripe", "role": "Backend Engineer", "date_applied": "2025-06-01"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["company"] == "Stripe"
    assert data["status"] == "Applied"


@pytest.mark.asyncio
async def test_list_applications(auth_client):
    await auth_client.post("/applications", json={
        "company": "Stripe", "role": "SWE", "date_applied": "2025-06-01"
    })
    res = await auth_client.get("/applications")
    assert res.status_code == 200
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_update_application(auth_client):
    create = await auth_client.post("/applications", json={
        "company": "Stripe", "role": "SWE", "date_applied": "2025-06-01"
    })
    app_id = create.json()["id"]
    res = await auth_client.patch(f"/applications/{app_id}", json={"status": "Interview"})
    assert res.status_code == 200
    assert res.json()["status"] == "Interview"


@pytest.mark.asyncio
async def test_delete_application(auth_client):
    create = await auth_client.post("/applications", json={
        "company": "Stripe", "role": "SWE", "date_applied": "2025-06-01"
    })
    app_id = create.json()["id"]
    res = await auth_client.delete(f"/applications/{app_id}")
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_stats(auth_client):
    await auth_client.post("/applications", json={
        "company": "Stripe", "role": "SWE", "date_applied": "2025-06-01"
    })
    res = await auth_client.get("/applications/stats")
    assert res.status_code == 200
    assert res.json()["total"] == 1


@pytest.mark.asyncio
async def test_unauthenticated(client):
    res = await client.get("/applications")
    assert res.status_code == 401
