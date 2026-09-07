from datetime import date, timedelta


APPLICATION = {
    "company": "Example",
    "role": "Intern",
    "date_applied": "2025-06-01",
    "notes": "Keep this note",
    "url": "https://example.com/jobs",
}


async def create_application(auth_client, **changes):
    response = await auth_client.post("/applications", json={**APPLICATION, **changes})
    assert response.status_code == 201
    return response.json()


async def test_long_search_returns_controlled_error(auth_client):
    response = await auth_client.get(
        "/applications", params={"search": "a" * 100, "status": "Applied"},
    )
    assert response.status_code == 200

    for params in [
        {"search": "a" * 101},
        {"search": "a" * 101, "status": "Applied"},
    ]:
        response = await auth_client.get("/applications", params=params)
        assert response.status_code == 400
        assert response.json() == {
            "detail": "Search query too long (max 100 characters)"
        }


async def test_patch_clears_nullable_fields_and_preserves_omitted_fields(auth_client):
    application = await create_application(auth_client)
    response = await auth_client.patch(
        f"/applications/{application['id']}", json={"notes": None, "url": None},
    )
    assert response.status_code == 200
    assert response.json()["notes"] is None
    assert response.json()["url"] is None
    assert response.json()["company"] == APPLICATION["company"]
    assert response.json()["role"] == APPLICATION["role"]
    assert response.json()["date_applied"] == APPLICATION["date_applied"]
    assert response.json()["status"] == "Applied"


async def test_patch_normalizes_empty_nullable_strings_to_null(auth_client):
    for payload in [{"notes": "", "url": ""}, {"notes": "   ", "url": "   "}]:
        application = await create_application(auth_client)
        response = await auth_client.patch(
            f"/applications/{application['id']}", json=payload,
        )
        assert response.status_code == 200
        assert response.json()["notes"] is None
        assert response.json()["url"] is None


async def test_create_and_patch_strip_application_text(auth_client):
    application = await create_application(
        auth_client,
        company="  Example  ",
        role="  Intern  ",
        notes="  Follow up  ",
        url="  https://example.com/jobs  ",
    )
    assert application["company"] == "Example"
    assert application["role"] == "Intern"
    assert application["notes"] == "Follow up"
    assert application["url"] == "https://example.com/jobs"

    response = await auth_client.patch(
        f"/applications/{application['id']}",
        json={"company": "  Other  ", "role": "  Engineer  ", "notes": "  New  "},
    )
    assert response.status_code == 200
    assert response.json()["company"] == "Other"
    assert response.json()["role"] == "Engineer"
    assert response.json()["notes"] == "New"
    assert response.json()["url"] == APPLICATION["url"]


async def test_required_fields_reject_blank_or_null_values(auth_client):
    application = await create_application(auth_client)
    app_id = application["id"]
    invalid_create_values = [
        {"company": ""}, {"company": "   "}, {"role": ""}, {"role": "   "},
        {"company": None}, {"role": None}, {"date_applied": None}, {"status": None},
    ]
    for changes in invalid_create_values:
        response = await auth_client.post(
            "/applications", json={**APPLICATION, **changes},
        )
        assert response.status_code == 422, changes

    for field, value in [
        ("company", ""), ("company", "   "), ("role", ""), ("role", "   "),
        ("company", None), ("role", None), ("date_applied", None), ("status", None),
    ]:
        response = await auth_client.patch(
            f"/applications/{app_id}", json={field: value},
        )
        assert response.status_code == 422, (field, value)


async def test_future_application_dates_are_rejected_consistently(auth_client):
    future = (date.today() + timedelta(days=1)).isoformat()
    response = await auth_client.post(
        "/applications", json={**APPLICATION, "date_applied": future},
    )
    assert response.status_code == 422

    application = await create_application(auth_client)
    response = await auth_client.patch(
        f"/applications/{application['id']}", json={"date_applied": future},
    )
    assert response.status_code == 422


async def test_string_limits_match_database_columns(auth_client):
    application = await create_application(auth_client)

    for field in ["company", "role"]:
        response = await auth_client.post(
            "/applications", json={**APPLICATION, field: "a" * 255},
        )
        assert response.status_code == 201, field

        response = await auth_client.patch(
            f"/applications/{application['id']}", json={field: "a" * 255},
        )
        assert response.status_code == 200, field
        assert response.json()[field] == "a" * 255

        response = await auth_client.post(
            "/applications", json={**APPLICATION, field: "a" * 256},
        )
        assert response.status_code == 422, field

        response = await auth_client.patch(
            f"/applications/{application['id']}", json={field: "a" * 256},
        )
        assert response.status_code == 422, field

    url_at_limit = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
    response = await auth_client.post(
        "/applications", json={**APPLICATION, "url": url_at_limit},
    )
    assert response.status_code == 201
    assert response.json()["url"] == url_at_limit

    response = await auth_client.patch(
        f"/applications/{application['id']}", json={"url": url_at_limit},
    )
    assert response.status_code == 200
    assert response.json()["url"] == url_at_limit

    response = await auth_client.post(
        "/applications", json={**APPLICATION, "url": f"{url_at_limit}a"},
    )
    assert response.status_code == 422

    response = await auth_client.patch(
        f"/applications/{application['id']}", json={"url": f"{url_at_limit}a"},
    )
    assert response.status_code == 422
