from contextlib import contextmanager
import os
import socket
import subprocess
import sys
import time

import httpx
from sqlalchemy.engine import make_url
import asyncpg

from test_migrations import BACKEND, alembic


@contextmanager
def running_api(database_url, log_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL=database_url, JWT_SECRET="rehearsal-only-secret-preserved-across-restarts",
        APP_ENV="production", FRONTEND_ORIGIN="https://frontend.example",
        TRUSTED_PROXY_IPS="", PORT=str(port), WEB_CONCURRENCY="4",
    )
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "start.py"], cwd=BACKEND, env=environment,
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    assert process.poll() is None, log_path.read_text()
                    try:
                        if client.get("/health/live").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("API did not start: " + log_path.read_text())
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def test_release_startup_migration_and_persistence(postgres_url, tmp_path):
    with running_api(postgres_url, tmp_path / "before-migration.log") as client:
        assert client.get("/health/ready").status_code == 503
    alembic(postgres_url, "upgrade", "head")
    credentials = {"email": "persist@example.com", "password": "password123"}
    with running_api(postgres_url, tmp_path / "first-start.log") as client:
        assert client.get("/health/ready").json() == {"status": "ready"}
        preflight = client.options("/register", headers={
            "Origin": "https://frontend.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert preflight.headers["access-control-allow-origin"] == "https://frontend.example"
        assert client.post("/register", json=credentials).status_code == 201
        login = client.post("/login", json=credentials)
        assert login.status_code == 200
        authorization = {"Authorization": "Bearer " + login.json()["access_token"]}
        created = client.post("/applications", headers=authorization, json={
            "company": "Survives restart", "role": "Intern", "date_applied": "2026-09-01",
            "notes": "stored in PostgreSQL",
        })
        assert created.status_code == 201
        application_id = created.json()["id"]
        # Direct requests cannot evade the limit by spoofing a forwarded address.
        for index in range(18):
            assert client.post("/login", json={}, headers={"X-Forwarded-For": f"203.0.113.{index}"}).status_code == 422
        assert client.post("/login", json={}).status_code == 429
        assert client.get("/health/ready").status_code == 200
    alembic(postgres_url, "upgrade", "head")
    with running_api(postgres_url, tmp_path / "second-start.log") as client:
        assert client.get("/health/ready").status_code == 200
        assert client.post("/login", json=credentials).status_code == 200
        rows = client.get("/applications", headers=authorization).json()
        assert len(rows) == 1 and rows[0]["id"] == application_id
        assert rows[0]["notes"] == "stored in PostgreSQL"
        assert client.delete(f"/applications/{application_id}", headers=authorization).status_code == 204
        assert client.get("/applications", headers=authorization).json() == []


async def test_readiness_rejects_bad_credentials_and_wrong_revision(postgres_url, tmp_path):
    bad_url = make_url(postgres_url).set(password="incorrect-password").render_as_string(hide_password=False)
    with running_api(bad_url, tmp_path / "bad-credentials.log") as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not ready"}
    alembic(postgres_url, "upgrade", "head")
    connection = await asyncpg.connect(postgres_url)
    try:
        await connection.execute("UPDATE alembic_version SET version_num = 'unexpected'")
        with running_api(postgres_url, tmp_path / "wrong-revision.log") as client:
            assert client.get("/health/ready").status_code == 503
    finally:
        await connection.close()
