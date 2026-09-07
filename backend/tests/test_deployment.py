import asyncio
from contextlib import asynccontextmanager
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from config import load_settings
from main import app
import main
from rate_limit import AuthRateLimiter


@pytest.mark.parametrize("name,value", [
    ("JWT_SECRET", ""), ("JWT_SECRET", "short"),
    ("JWT_SECRET", " " + "a" * 32), ("APP_ENV", "prod"),
    ("FRONTEND_ORIGIN", ""), ("FRONTEND_ORIGIN", "*"),
    ("FRONTEND_ORIGIN", "https://example.com/"),
    ("FRONTEND_ORIGIN", "https://user:password@example.com"),
    ("FRONTEND_ORIGIN", "https://@example.com"),
    ("FRONTEND_ORIGIN", "https://example.com\\unexpected"),
    ("FRONTEND_ORIGIN", "https://example.com:bad"),
    ("TRUSTED_PROXY_IPS", "*"), ("TRUSTED_PROXY_IPS", "0.0.0.0/0"),
])
def test_invalid_settings_fail_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises((RuntimeError, ValueError)):
        load_settings()


def test_production_requires_postgres_and_https(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="HTTPS"):
        load_settings()
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://one.example,https://two.example")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        load_settings()
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/unused")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,10.0.0.0/24")
    assert load_settings().origins == ("https://one.example", "https://two.example")


async def test_cors_only_allows_configured_origin_and_headers(client):
    for origin, status in [("http://localhost:5500", 200), ("https://evil.example", 400)]:
        response = await client.options("/login", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        })
        assert response.status_code == status
        assert (response.headers.get("access-control-allow-origin") == origin) == (status == 200)
        assert "access-control-allow-credentials" not in response.headers
    response = await client.options("/login", headers={
        "Origin": "http://localhost:5500", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-unapproved",
    })
    assert response.status_code == 400


async def test_auth_limit_counts_invalid_requests_and_ignores_spoofed_headers(client, monkeypatch):
    now = [0]
    limiter = AuthRateLimiter(per_client=2, clock=lambda: now[0])
    monkeypatch.setattr(app.state, "auth_limiter", limiter)
    assert (await client.post("/login", json={})).status_code == 422
    assert (await client.post("/register", json={})).status_code == 422
    response = await client.post("/login", json={}, headers={
        "X-Forwarded-For": "203.0.113.9", "Origin": "http://localhost:5500",
    })
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5500"
    assert (await client.get("/health/live")).status_code == 200
    now[0] = 60
    assert (await client.post("/login", json={})).status_code == 422


def test_auth_limit_bounds_distinct_clients_and_expires():
    now = [0]
    limiter = AuthRateLimiter(per_client=2, total=3, clock=lambda: now[0])
    assert limiter.retry_after("one") == 0
    assert limiter.retry_after("one") == 0
    assert limiter.retry_after("one") == 60
    assert limiter.retry_after("two") == 0
    for index in range(1000):
        assert limiter.retry_after(str(index)) == 60
    assert len(limiter.clients) == 2
    now[0] = 61
    assert limiter.retry_after("three") == 0
    assert limiter.clients == {"three": 1}


async def test_concurrent_auth_requests_share_one_budget(client, monkeypatch):
    monkeypatch.setattr(app.state, "auth_limiter", AuthRateLimiter(per_client=2))
    responses = await asyncio.gather(*(client.post("/login", json={}) for _ in range(10)))
    assert sorted(response.status_code for response in responses) == [422] * 2 + [429] * 8


async def test_health_does_not_leak_database_failures(client, monkeypatch):
    # The SQLite test schema has no migration version, so it is not deployment-ready.
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}

    @asynccontextmanager
    async def unavailable():
        raise OperationalError("secret database address", {}, Exception("private password"))
        yield

    monkeypatch.setattr(main, "engine", SimpleNamespace(connect=unavailable))
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}
    assert response.headers["cache-control"] == "no-store"


def test_frontend_build_is_explicit_and_only_contains_public_configuration(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_frontend.py"
    spec = importlib.util.spec_from_file_location("build_frontend", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("JWT_SECRET", "must-not-be-in-static-files")
    output = tmp_path / "site"
    for invalid in ["", "http://api.example", "javascript:alert(1)", "https://user:pw@api.example", "https://@api.example", "https://api.example/path"]:
        with pytest.raises(ValueError):
            module.build(invalid, output)
        assert not output.exists()
    module.build("https://api.example/", output)
    config = (output / "config.js").read_text()
    assert json.loads(config.removeprefix("window.APPLYVAULT_CONFIG = ").strip().removesuffix(";")) == {
        "apiUrl": "https://api.example",
    }
    assert all("must-not-be-in-static-files" not in path.read_text(encoding="utf-8") for path in output.iterdir())
    for name in ["index.html", "dashboard.html"]:
        content = (output / name).read_text(encoding="utf-8")
        assert content.index('src="config.js"') < content.index('src="app.js"')
