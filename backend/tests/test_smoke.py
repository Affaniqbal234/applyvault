import pytest


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
