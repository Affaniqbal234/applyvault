# Deployment configuration

ApplyVault runs as one Python 3.12 API process, a static frontend, and a persistent
PostgreSQL database. Use the latest available Python 3.12 security patch. The
repository's `.python-version` and CI declare the supported minor version.
Deployment requires separate approval; these commands prepare a release.

## API service

Set the service root to `backend/` and configure:

| Setting | Value |
| --- | --- |
| Build | `python -m pip install -r requirements.txt` |
| Pre-deploy/release | `python -m alembic upgrade head` |
| Start | `python start.py` |
| Health check path | `/health/ready` |
| Processes/replicas | One worker, one replica |

`backend/Procfile` uses the same start command. `start.py` binds to `0.0.0.0` on
`PORT` (default `8000`), explicitly selects one worker, limits concurrent
connections to 64, and disables forwarded-header trust unless configured.
Run the migration once before starting the new application version. For an
existing database, first follow [database adoption](database-migrations.md).

Set these values in the host's environment/secret manager:

| Variable | Required value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | PostgreSQL URL for persistent storage; never SQLite or a local ephemeral file |
| `JWT_SECRET` | Independently generated random secret, at least 32 bytes |
| `FRONTEND_ORIGIN` | Exact HTTPS frontend origin; comma-separated for multiple origins, no paths or trailing slashes |
| `PORT` | Supplied by the host, or explicitly set for your service |
| `TRUSTED_PROXY_IPS` | Empty for direct connections; otherwise verified proxy IPs/CIDRs |

Generate a secret locally with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`, then store it in
the host's secret manager. Do not put it in source, build logs, frontend settings,
or a deployment manifest. Keep the same secret across restarts. Rotating it
invalidates existing JWT sessions, which otherwise expire after 24 hours.

The API rejects missing/short secrets, wildcard or malformed origins, production
HTTP origins, and a non-PostgreSQL production URL. Environment variables override
the local `.env` file. CORS allows bearer authorization and JSON requests from
configured origins; it is not a replacement for authentication.

Terminate HTTPS at the host's reverse proxy and require HTTPS on public API and
frontend URLs. Restrict database access to the API and migration operator; use
the database provider's verified TLS connection settings for remote connections.
Configure backups and rehearse restoration before storing real application data.
TLS, network access, and backup schedules are host settings, not checks this
repository can prove locally.

## Proxy trust and authentication limits

Login and registration share a fixed 60-second window: at most 20 requests per
client IP and 100 requests across the process. Successful, failed, and malformed
attempts count. Excess requests receive `429` with `Retry-After`; health and
authenticated application operations remain available. The global limit also
bounds the number of stored client counters. A window boundary permits a burst
across two windows; this is a basic throttle, not a distributed abuse service.

The counters live in memory and reset on restart. Keep one process and one
replica. Before scaling, use an atomic shared limiter or enforce equivalent
limits at a trusted gateway. Shared networks can exhaust the per-IP allowance;
monitor `429` rates before changing the limits.

The application uses the client address resolved by Uvicorn. For a reverse proxy,
verify its source addresses and that it strips/replaces client-supplied forwarding
headers before setting `TRUSTED_PROXY_IPS`. Wildcards and all-address CIDRs are
rejected. With no proxy trust, users behind a proxy share that proxy's limit.
Do not deploy until this configuration is checked on the intended host. Use the
gateway's request-size and connection limits for traffic the application cannot
handle economically. See [Uvicorn proxy settings](https://www.uvicorn.org/settings/#http).

## Static frontend

The static build needs Python 3.12 and one public setting: `API_URL`, the HTTPS
API origin without credentials or a path. From the repository root:

```bash
API_URL=https://api.example.com python scripts/build_frontend.py
```

In PowerShell:

```powershell
$env:API_URL = 'https://api.example.com'
python scripts/build_frontend.py
```

Publish `dist/frontend/` after deployment approval. The build copies an explicit
list of public files and writes `config.js`; it does not read `.env` or copy
backend files. Both pages load the configuration before `app.js`. Missing or
invalid configuration disables requests and shows an error. Local development
uses the checked-in `frontend/config.js` pointing to `http://localhost:8000`.

Set `Cache-Control: no-cache` for HTML, `config.js`, and `app.js` on the static
host so a release does not keep an obsolete API origin or script. Set
`FRONTEND_ORIGIN` to the actual published frontend origin, including any preview
origin that should be allowed. Do not allow arbitrary preview subdomains.

## Health and release rehearsal

`GET /health/live` returns `200` when the API can serve requests, independent of
the database. `GET /health/ready` checks database connectivity and the Alembic
revision against the code's migration head. It returns `503` for an unavailable
database or missing/wrong revision, with a three-second database-check timeout.
It exposes no exception details and makes no schema changes. A matching revision
does not prove there is no schema drift; use `alembic check` during releases.

Install `backend/requirements-dev.txt`, set `POSTGRES_BIN` when necessary, and run
from the repository root:

```bash
python -m pytest integration_tests/ -q
```

The deployment rehearsal starts the real `start.py` process against disposable
PostgreSQL. It verifies liveness before migration, readiness after migration,
CORS preflight, register/login/create, throttling with spoofed forwarding headers,
and persistence after stopping/restarting the API and repeating `upgrade head`.
The retained JWT and a new login must both work after restart; the stored row is
then deleted. Tests never select a database from inherited application settings.

Before approving a hosted deployment, repeat the flow through its actual HTTPS
frontend and proxy. Verify allowed/disallowed origins, client address resolution,
health behavior, persistence after restart/redeploy, and backup restoration.
The local rehearsal cannot verify those provider settings.

## Dependency review

`backend/requirements.in` lists direct production dependencies;
`backend/requirements.txt` locks their transitive versions
for supported platforms. Tests use `requirements-dev.txt`; browser tests add
`requirements-browser.txt`. Test tools are not installed by the production build.

To refresh the production lock after reviewing a dependency update:

```bash
uv pip compile --python 3.12 --universal backend/requirements.in -o backend/requirements.txt
python -m pip install pip-audit==2.10.1
python -m pip_audit --no-deps --disable-pip -r backend/requirements.txt
```

CI audits the complete production lock without resolving a different set of
packages. Review advisories and release notes, then run backend, browser, and
PostgreSQL tests before accepting updates. A clean audit means no known advisory
was reported by that scan; it does not prove the software has no vulnerabilities.

The 2026-09-07 review updated FastAPI/Starlette, PyJWT, python-dotenv, and pytest
after advisory findings, and updated pytest-asyncio for pytest compatibility.
The resulting production lock and resolved development/browser dependencies
passed `pip-audit` without ignored advisories. The application retains explicit
JWT algorithm validation and now requires at least 32-byte secrets. Relevant
upstream notes: [PyJWT](https://pyjwt.readthedocs.io/en/stable/changelog.html),
[Starlette](https://www.starlette.io/release-notes/), and
[pytest-asyncio](https://pytest-asyncio.readthedocs.io/en/stable/reference/changelog.html).
