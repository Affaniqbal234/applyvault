from playwright.async_api import expect
from sqlalchemy import update

from database import SessionLocal
from models import Application


DASHBOARD = "http://localhost:5500/dashboard.html"
APPLICATION = {
    "company": "Example", "role": "Intern", "date_applied": "2025-06-01",
}


async def test_stored_text_stays_inert_through_edit_save_reload_and_delete(page, auth_client):
    stored = {
        **APPLICATION,
        "company": '&quot;});window.__unsafe=1;//',
        "role": '<img src=x onerror="window.__unsafe=1">',
        "notes": 'Quotes: " \' & <script>window.__unsafe=1</script> &#34;',
        "url": "https://example.com/jobs?team=R%26D&role=intern",
    }
    created = await auth_client.post("/applications", json=stored)
    assert created.status_code == 201
    await page.goto(DASHBOARD)
    await expect(page.locator(".app-card-company")).to_have_text(stored["company"])
    await expect(page.locator(".app-card-role")).to_have_text(stored["role"])
    await expect(page.locator(".app-card-notes")).to_have_text(stored["notes"])
    await expect(page.locator(".app-card img, .app-card script")).to_have_count(0)

    await page.get_by_role("button", name="Edit", exact=True).click()
    assert await page.evaluate("window.__unsafe === undefined")
    await expect(page.locator("#field-company")).to_have_value(stored["company"])
    await expect(page.locator("#field-notes")).to_have_value(stored["notes"])
    await expect(page.locator("[onclick]")).to_have_count(0)
    await page.get_by_role("button", name="Save", exact=True).click()
    await expect(page.locator("#modal-overlay")).to_be_hidden()

    saved = (await auth_client.get("/applications")).json()[0]
    for field, value in stored.items():
        assert saved[field] == value
    await page.reload()
    await page.get_by_role("button", name="Edit", exact=True).click()
    await expect(page.locator("#field-role")).to_have_value(stored["role"])
    assert await page.evaluate("window.__unsafe === undefined")
    await page.locator("#modal-cancel-btn").click()
    page.once("dialog", lambda dialog: dialog.accept())
    await page.get_by_role("button", name="Delete", exact=True).click()
    await expect(page.locator(".app-card")).to_have_count(0)
    assert (await auth_client.get("/applications")).json() == []


async def test_validation_errors_render_as_text(page):
    hostile = '<img src=x onerror="window.__unsafe=1">'
    await page.goto(DASHBOARD)
    await page.locator("#add-btn").click()
    await page.locator("#field-company").fill("Example")
    await page.locator("#field-role").fill("Intern")
    await page.locator("#field-date").fill("2025-06-01")
    # An invalid enum is echoed in FastAPI's structured validation error.
    await page.locator("#field-status").evaluate(
        "(select, value) => { select.add(new Option(value, value)); select.value = value; }",
        hostile,
    )
    await page.get_by_role("button", name="Save", exact=True).click()
    await expect(page.locator(".toast")).to_contain_text("window.__unsafe=1")
    await expect(page.locator(".toast img")).to_have_count(0)
    assert await page.evaluate("window.__unsafe === undefined")


async def test_string_errors_render_as_text(page):
    hostile = '<img src=x onerror="window.__unsafe=1">'
    await page.route(
        "http://localhost:8000/applications",
        lambda route: route.fulfill(status=400, json={"detail": hostile}),
    )
    await page.goto(DASHBOARD)
    await expect(page.locator(".toast")).to_contain_text(hostile)
    await expect(page.locator(".toast img")).to_have_count(0)
    assert await page.evaluate("window.__unsafe === undefined")


async def test_legacy_unsafe_urls_are_not_links(page, auth_client):
    urls = [
        "javascript:window.__unsafe=1", "JaVaScRiPt:window.__unsafe=1",
        "java\nscript:window.__unsafe=1", "data:text/html,<script>alert(1)</script>",
        "file:///tmp/posting", "//example.com/jobs", "/jobs", "not a URL",
        "http://example.com/jobs", "https://example.com/jobs?x=1&y=2",
    ]
    for index, url in enumerate(urls):
        created = await auth_client.post(
            "/applications", json={**APPLICATION, "company": str(index)},
        )
        assert created.status_code == 201
        # Simulate records saved before URL validation existed.
        async with SessionLocal() as session:
            await session.execute(
                update(Application).where(Application.id == created.json()["id"]).values(url=url)
            )
            await session.commit()
    await page.goto(DASHBOARD)
    links = page.locator(".app-card-url")
    await expect(links).to_have_count(2)
    assert set(await links.evaluate_all("links => links.map(link => link.href)")) == set(urls[-2:])
    for link in await links.all():
        await expect(link).to_have_attribute("target", "_blank")
        await expect(link).to_have_attribute("rel", "noopener noreferrer")


async def test_form_rejects_unsafe_url_before_sending(page, auth_client):
    await page.goto(DASHBOARD)
    await page.locator("#add-btn").click()
    await page.locator("#field-company").fill("Example")
    await page.locator("#field-role").fill("Intern")
    await page.locator("#field-date").fill("2025-06-01")
    requests = []
    page.on("request", lambda request: requests.append(request.method))
    for url in ["javascript:alert(1)", "//example.com/jobs", "not a URL"]:
        await page.locator("#field-url").fill(url)
        await page.get_by_role("button", name="Save", exact=True).click()
        await expect(page.locator("#app-form-error")).to_have_text(
            "Job posting URL must be an absolute HTTP or HTTPS URL."
        )
    assert "POST" not in requests
    assert (await auth_client.get("/applications")).json() == []
