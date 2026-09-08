# Deployment

ApplyVault uses a static frontend on Vercel, a FastAPI service on Render, and
Neon PostgreSQL for persistent storage.

## Frontend: Vercel

Production: [applyvault.vercel.app](https://applyvault.vercel.app)

Production project settings:

| Setting | Value |
| --- | --- |
| Framework preset | Other |
| Root directory | `./` |
| Build command | `python3 scripts/build_frontend.py` |
| Output directory | `dist/frontend` |
| Install command | Blank |
| Environment variable | `API_URL=https://applyvault-api.onrender.com` |

The build writes the public API origin to `config.js`.
Rebuild after changing `API_URL`. Publish only `dist/frontend`; database credentials
and `JWT_SECRET` belong in Render's environment settings.

## API: Render

Production API origin: `https://applyvault-api.onrender.com`
([API docs](https://applyvault-api.onrender.com/docs)).

Production service settings:

| Setting | Value |
| --- | --- |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m alembic upgrade head && python start.py` |
| Health check path | `/health/ready` |
| Auto-deploy | After CI checks pass |

Production environment variables (credentials omitted):

| Variable | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.12.14` |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Direct Neon asyncpg URL, as described below |
| `JWT_SECRET` | Secret of at least 32 bytes, kept stable across restarts |
| `FRONTEND_ORIGIN` | `https://applyvault.vercel.app` |
| `PORT` | Supplied by Render; the script defaults to `8000` |
| `TRUSTED_PROXY_IPS` | Empty; forwarded-header trust is disabled |
| `PGSSLROOTCERT` | `/etc/ssl/certs/ca-certificates.crt` |

`FRONTEND_ORIGIN` controls CORS. Additional allowed origins must be explicit,
comma-separated HTTPS origins without paths, wildcards, or trailing slashes.
Authentication limits are held in memory, so keep one instance. Without trusted
proxy addresses, users behind the same proxy share its per-IP limit.

Render runs Alembic on every service start through the configured start command.
The `&&` starts the API only if migrations succeed. There is no separate pre-deploy
command. Follow
[database adoption](database-migrations.md#adopting-an-existing-database) first
if the database already contains tables without an Alembic revision.

[Render free web services](https://render.com/docs/free#spinning-down-on-idle) sleep
after 15 minutes without traffic. The first API request after idle can take about
a minute while the service starts.

## Database: Neon PostgreSQL

The API and Alembic use a direct, non-pooled Neon connection through SQLAlchemy's
asyncpg driver. Set `DATABASE_URL` using this placeholder format:

```text
postgresql+asyncpg://<user>:<password>@<direct-neon-host>/<database>?ssl=verify-full
```

`ssl=verify-full` verifies the server certificate and hostname. Render supplies the
trusted CA certificates through `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt`.
Percent-encode special characters in credentials.

Keep backups before schema changes. See [database migrations](database-migrations.md)
for upgrades, existing database adoption, and destructive downgrade behavior.

## Health checks

- `GET /health/live`: returns `200` when the API can serve requests, independently
  of the database.
- `GET /health/ready`: returns `200` when the database is reachable and its Alembic
  revision matches the code's migration head; otherwise returns `503`. The
  database check has a three-second timeout.

Health checks make no schema changes. Readiness checks the revision, not schema
drift; use `python -m alembic check` when applying migrations.
