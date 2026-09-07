async def test_authenticated_user_endpoint_returns_only_email(auth_client):
    response = await auth_client.get("/me")

    assert response.status_code == 200
    assert response.json() == {"email": "test@example.com"}


async def test_authenticated_user_endpoint_requires_token(client):
    response = await client.get("/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
