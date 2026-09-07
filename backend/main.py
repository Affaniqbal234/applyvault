import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from alembic.config import Config
from alembic.script import ScriptDirectory
from asyncpg import PostgresError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from database import engine
from rate_limit import AuthRateLimiter
from routers import applications, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="ApplyVault", lifespan=lifespan)
app.state.auth_limiter = AuthRateLimiter()
expected_revision = ScriptDirectory.from_config(
    Config(str(Path(__file__).with_name("alembic.ini")))
).get_current_head()


@app.middleware("http")
async def limit_authentication(request, call_next):
    if request.method == "POST" and request.url.path.rstrip("/") in {"/login", "/register"}:
        client = request.client.host if request.client else "unknown"
        retry_after = app.state.auth_limiter.retry_after(client)
        if retry_after:
            return JSONResponse(
                {"detail": "Too many authentication attempts. Try again later."},
                status_code=429, headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After"],
)


@app.get("/health/live", include_in_schema=False)
async def live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def ready():
    async def check_database():
        async with engine.connect() as connection:
            revisions = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
            return revisions == [expected_revision]

    try:
        if await asyncio.wait_for(check_database(), timeout=3):
            return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError):
        pass
    return JSONResponse(
        {"status": "not ready"}, status_code=503, headers={"Cache-Control": "no-store"},
    )

app.include_router(auth.router, tags=["auth"])
app.include_router(applications.router)
