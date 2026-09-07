import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest_asyncio
from playwright.async_api import async_playwright


FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def open_frontend(client, token=None):
    # Route the real frontend to the ASGI client and its test-owned database.
    # No running API, external network, or application database is needed.
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        async def serve_request(route):
            request = route.request
            url = urlsplit(request.url)
            if url.netloc == "localhost:8000":
                response = await client.request(
                    request.method,
                    url.path + (f"?{url.query}" if url.query else ""),
                    content=request.post_data_buffer,
                    headers=request.headers,
                )
                await route.fulfill(
                    status=response.status_code,
                    headers={
                        **response.headers,
                        "access-control-allow-origin": "http://localhost:5500",
                    },
                    body=response.content,
                )
            elif url.netloc == "localhost:5500" and url.path in {
                "/index.html", "/dashboard.html", "/app.js", "/config.js", "/style.css",
            }:
                await route.fulfill(path=FRONTEND / url.path.lstrip("/"))
            else:
                await route.abort()

        await context.route("**/*", serve_request)
        if token is not None:
            await context.add_init_script(
                f"localStorage.setItem('token', {json.dumps(token)});"
            )
        try:
            yield page
        finally:
            await context.close()
            await browser.close()
        assert errors == []


@pytest_asyncio.fixture
async def anonymous_page(client):
    async with open_frontend(client) as browser_page:
        yield browser_page


@pytest_asyncio.fixture
async def page(auth_client):
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    async with open_frontend(auth_client, token) as browser_page:
        yield browser_page
