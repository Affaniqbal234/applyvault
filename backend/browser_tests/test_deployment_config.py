from playwright.async_api import expect


async def test_frontend_uses_explicit_api_origin(anonymous_page):
    page = anonymous_page
    requests = []
    await page.route("**/config.js", lambda route: route.fulfill(
        content_type="application/javascript",
        body='window.APPLYVAULT_CONFIG = {apiUrl: "https://configured-api.example"};',
    ))

    async def login(route):
        requests.append(route.request.url)
        await route.fulfill(status=401, json={"detail": "Configured API reached"}, headers={
            "access-control-allow-origin": "http://localhost:5500",
        })

    await page.route("https://configured-api.example/login", login)
    await page.goto("http://localhost:5500/index.html")
    await page.locator("#login-email").fill("config@example.com")
    await page.locator("#login-password").fill("password123")
    await page.get_by_role("button", name="Sign In").click()
    await expect(page.locator("#login-error")).to_have_text("Configured API reached")
    assert requests == ["https://configured-api.example/login"]


async def test_missing_configuration_disables_requests(anonymous_page):
    page = anonymous_page
    await page.route("**/config.js", lambda route: route.fulfill(
        content_type="application/javascript", body="// missing configuration",
    ))
    await page.goto("http://localhost:5500/index.html")
    await expect(page.get_by_role("button", name="Sign In")).to_be_disabled()
    await expect(page.locator(".toast")).to_contain_text("Service configuration is unavailable")
    assert await page.evaluate("api('/me')") == {"ok": False, "data": None}
