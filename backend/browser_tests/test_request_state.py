import asyncio
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import expect


INDEX = "http://localhost:5500/index.html"
DASHBOARD = "http://localhost:5500/dashboard.html"


def application(application_id, company):
    return {
        "id": application_id,
        "company": company,
        "role": "Software Engineer",
        "status": "Applied",
        "date_applied": "2025-06-01",
        "notes": None,
        "url": None,
        "created_at": "2025-06-01T12:00:00",
        "updated_at": "2025-06-01T12:00:00",
    }


async def test_register_to_delete_browser_flow_uses_server_email(anonymous_page):
    page = anonymous_page
    await page.goto(INDEX)

    await page.get_by_role("tab", name="Create Account").click()
    await page.locator("#register-email").fill("browser-flow@example.com")
    await page.locator("#register-password").fill("password123")
    await page.get_by_role("button", name="Create Account").click()
    await expect(page.locator("#register-success")).to_have_text(
        "Account created! You can now sign in."
    )
    await expect(page.locator("#panel-login")).to_be_visible(timeout=3_000)

    await page.locator("#login-email").fill("browser-flow@example.com")
    await page.locator("#login-password").fill("password123")
    await page.get_by_role("button", name="Sign In").click()
    await expect(page).to_have_url(DASHBOARD)
    await expect(page.locator("#user-email")).to_have_text("browser-flow@example.com")

    await page.locator("#add-btn").click()
    await page.locator("#field-company").fill("Example Company")
    await page.locator("#field-role").fill("Software Engineer")
    await page.locator("#field-date").fill("2025-06-01")
    await page.get_by_role("button", name="Save", exact=True).click()
    await expect(page.locator(".app-card-company")).to_have_text("Example Company")
    await expect(page.locator("#stat-total")).to_have_text("1")

    page.once("dialog", lambda dialog: dialog.accept())
    await page.get_by_role("button", name="Delete", exact=True).click()
    await expect(page.locator(".app-card")).to_have_count(0)
    await expect(page.locator(".empty-state h3")).to_have_text("No applications found")
    await expect(page.locator("#stat-total")).to_have_text("0")


async def test_application_error_does_not_render_as_empty_result(page, auth_client):
    created = await auth_client.post(
        "/applications",
        json={
            "company": "Existing Company",
            "role": "Engineer",
            "date_applied": "2025-06-01",
        },
    )
    assert created.status_code == 201

    async def filtered_response(route):
        search = parse_qs(urlsplit(route.request.url).query).get("search", [""])[0]
        if search == "failure":
            await route.fulfill(status=500, json={"detail": "Search unavailable"})
        else:
            await route.fulfill(status=200, json=[])

    await page.route("**/applications?*", filtered_response)
    await page.goto(DASHBOARD)
    await expect(page.locator(".app-card-company")).to_have_text("Existing Company")

    await page.locator("#search-input").fill("failure")
    await expect(page.locator(".toast")).to_contain_text("Search unavailable")
    await expect(page.locator(".app-card-company")).to_have_text("Existing Company")
    await expect(page.locator(".empty-state")).to_have_count(0)

    await page.locator("#search-input").fill("missing")
    await expect(page.locator(".app-card")).to_have_count(0)
    await expect(page.locator(".empty-state h3")).to_have_text("No applications found")


async def test_slow_search_cannot_replace_newer_results(page):
    slow_started = asyncio.Event()
    release_slow = asyncio.Event()
    slow_finished = asyncio.Event()

    async def search_response(route):
        search = parse_qs(urlsplit(route.request.url).query).get("search", [""])[0]
        if search == "slow":
            slow_started.set()
            await release_slow.wait()
            await route.fulfill(json=[application(1, "Stale Company")])
            slow_finished.set()
        else:
            await route.fulfill(json=[application(2, "Current Company")])

    await page.route("**/applications?*", search_response)
    await page.goto(DASHBOARD)

    try:
        await page.locator("#search-input").fill("slow")
        await asyncio.wait_for(slow_started.wait(), timeout=2)
        await page.locator("#search-input").fill("current")
        await expect(page.locator(".app-card-company")).to_have_text("Current Company")
    finally:
        release_slow.set()

    await asyncio.wait_for(slow_finished.wait(), timeout=2)
    await expect(page.locator(".app-card-company")).to_have_text("Current Company")
    await expect(page.get_by_text("Stale Company", exact=True)).to_have_count(0)
