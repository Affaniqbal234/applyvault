async def register_and_login(client, email):
    credentials = {"email": email, "password": "password123"}
    assert (await client.post("/register", json=credentials)).status_code == 201
    response = await client.post("/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_two_users_can_only_read_and_modify_their_own_applications(client):
    first = await register_and_login(client, "first@example.com")
    second = await register_and_login(client, "second@example.com")
    applications = []
    for headers, status in [(first, "Applied"), (second, "Interview")]:
        response = await client.post(
            "/applications", headers=headers,
            json={
                "company": "Shared search term", "role": "Intern",
                "date_applied": "2025-06-01", "status": status,
                "notes": f"Private {status} notes",
            },
        )
        assert response.status_code == 201
        applications.append(response.json())

    for headers, own, other in [
        (first, applications[0], applications[1]),
        (second, applications[1], applications[0]),
    ]:
        for params in [{}, {"search": "Shared"}, {"status": own["status"]}]:
            response = await client.get("/applications", headers=headers, params=params)
            assert response.status_code == 200
            assert response.json() == [own]
        response = await client.get(
            "/applications", headers=headers, params={"status": other["status"]},
        )
        assert response.status_code == 200
        assert response.json() == []
        response = await client.get("/applications/stats", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "total": 1,
            "by_status": {
                status: int(status == own["status"])
                for status in ["Applied", "Interview", "Offer", "Rejected", "Withdrawn"]
            },
        }
        response = await client.patch(
            f"/applications/{other['id']}", headers=headers,
            json={"notes": "Overwritten", "status": "Offer"},
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Application not found"}
        response = await client.delete(f"/applications/{other['id']}", headers=headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Application not found"}

    for headers, own in [(first, applications[0]), (second, applications[1])]:
        response = await client.get("/applications", headers=headers)
        assert response.json() == [own]
        response = await client.patch(
            f"/applications/{own['id']}", headers=headers, json={"notes": "My update"},
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "My update"
        assert (await client.delete(f"/applications/{own['id']}", headers=headers)).status_code == 204
        assert (await client.get("/applications", headers=headers)).json() == []
