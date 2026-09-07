import os
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import uuid

import asyncpg
import pytest
import pytest_asyncio


def postgres_binary(name):
    directory = os.environ.get("POSTGRES_BIN")
    binary = shutil.which(name, path=directory) if directory else shutil.which(name)
    if not binary:
        pytest.fail(f"{name} is required. Set POSTGRES_BIN to PostgreSQL's bin directory.")
    return binary


@pytest.fixture(scope="session")
def postgres_cluster():
    with tempfile.TemporaryDirectory(prefix="applyvault-postgres-") as temporary:
        directory = Path(temporary)
        if os.name == "nt":
            # PostgreSQL drops administrator privileges. Python may create an
            # admin-owned directory, so grant the actual user access to this
            # newly created directory and its children only.
            owner = subprocess.check_output(["whoami"], text=True).strip()
            subprocess.run(
                ["icacls", str(directory), "/grant", f"{owner}:(OI)(CI)F"],
                check=True, capture_output=True, timeout=10,
            )
        yield from run_cluster(directory)


def run_cluster(directory):
    # Never connect to DATABASE_URL or an existing server. Own the entire cluster.
    data = directory / "data"
    password = uuid.uuid4().hex
    password_file = directory / "password"
    password_file.write_text(password, encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    initdb = postgres_binary("initdb")
    pg_ctl = postgres_binary("pg_ctl")
    subprocess.run(
        [initdb, "-D", str(data), "-U", "test_owner", "--auth=scram-sha-256",
         "--pwfile", str(password_file), "--encoding=UTF8", "--locale=C"],
        env=environment, check=True, capture_output=True, text=True, timeout=60,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    try:
        started = subprocess.run(
            [pg_ctl, "-D", str(data), "-l", str(directory / "postgres.log"),
             "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"],
            # Windows' server launcher can inherit captured pipes and keep
            # communicate() waiting after pg_ctl exits. Server output goes to -l.
            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
        )
        assert started.returncode == 0, (directory / "postgres.log").read_text(errors="replace")
        yield f"postgresql://test_owner:{password}@127.0.0.1:{port}"
    finally:
        status = subprocess.run(
            [pg_ctl, "-D", str(data), "status"], env=environment,
            capture_output=True, timeout=10,
        )
        if status.returncode == 0:
            subprocess.run(
                [pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"],
                env=environment, check=True, capture_output=True, timeout=60,
            )


@asynccontextmanager
async def isolated_database(postgres_cluster):
    name = "test_" + uuid.uuid4().hex
    admin = await asyncpg.connect(f"{postgres_cluster}/postgres")
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        try:
            yield f"{postgres_cluster}/{name}"
        finally:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest_asyncio.fixture
async def postgres_url(postgres_cluster):
    async with isolated_database(postgres_cluster) as url:
        yield url


@pytest_asyncio.fixture
async def rehearsal_url(postgres_cluster):
    async with isolated_database(postgres_cluster) as url:
        yield url


@pytest.fixture
def postgres_cli():
    def run(name, *arguments):
        result = subprocess.run(
            [postgres_binary(name), *arguments], capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return run
