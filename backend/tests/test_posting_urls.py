APPLICATION = {
    "company": "Example", "role": "Intern", "date_applied": "2025-06-01",
}


async def test_create_and_patch_reject_unsafe_posting_urls(auth_client):
    created = await auth_client.post(
        "/applications", json={**APPLICATION, "url": "https://example.com/jobs"},
    )
    assert created.status_code == 201
    app_id = created.json()["id"]
    for url in [
        "javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\nscript:alert(1)",
        "data:text/html,<script>alert(1)</script>", "file:///tmp/posting",
        "ftp://example.com/jobs", "//example.com/jobs", "/jobs", "not a URL",
        "https://", "https:example.com",
    ]:
        response = await auth_client.post("/applications", json={**APPLICATION, "url": url})
        assert response.status_code == 422, url
        response = await auth_client.patch(f"/applications/{app_id}", json={"url": url})
        assert response.status_code == 422, url
    applications = (await auth_client.get("/applications")).json()
    assert len(applications) == 1
    assert applications[0]["url"] == "https://example.com/jobs"


async def test_create_and_patch_accept_http_and_https_urls(auth_client):
    created = await auth_client.post("/applications", json=APPLICATION)
    assert created.status_code == 201
    app_id = created.json()["id"]
    for url in ["http://example.com/jobs", "https://example.com/jobs?x=1&y=2", "HTTPS://example.com/jobs"]:
        response = await auth_client.post("/applications", json={**APPLICATION, "url": f" {url} "})
        assert response.status_code == 201
        assert response.json()["url"] == url
        response = await auth_client.patch(f"/applications/{app_id}", json={"url": f" {url} "})
        assert response.status_code == 200
        assert response.json()["url"] == url


async def test_posting_url_remains_optional(auth_client):
    for extra in [{}, {"url": None}, {"url": ""}]:
        response = await auth_client.post("/applications", json={**APPLICATION, **extra})
        assert response.status_code == 201
        assert response.json()["url"] is None
