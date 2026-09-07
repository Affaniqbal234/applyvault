async def test_api_can_write_to_the_test_owned_database(client):
    response = await client.post(
        "/register",
        json={"email": "probe@example.com", "password": "password123"},
    )

    assert response.status_code == 201
