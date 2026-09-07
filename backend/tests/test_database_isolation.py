import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def test_inherited_database_url_is_never_used(tmp_path):
    sentinel_database = tmp_path / "application.db"
    marker = "must survive the test run"

    with sqlite3.connect(sentinel_database) as connection:
        connection.execute("CREATE TABLE sentinel (marker TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES (?)", (marker,))

    contents_before_test = sentinel_database.read_bytes()
    environment = os.environ.copy()
    environment["DATABASE_URL"] = sqlite_url(sentinel_database)

    backend_directory = Path(__file__).resolve().parents[1]
    probe = backend_directory / "tests" / "support" / "isolation_probe.py"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(probe),
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=backend_directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert sentinel_database.read_bytes() == contents_before_test

    with sqlite3.connect(sentinel_database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        stored_marker = connection.execute(
            "SELECT marker FROM sentinel"
        ).fetchone()[0]

    assert tables == {"sentinel"}
    assert stored_marker == marker


def test_harness_fails_closed_if_database_was_already_imported(tmp_path):
    sentinel_database = tmp_path / "preloaded-application.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = sqlite_url(sentinel_database)
    environment["JWT_SECRET"] = "disposable-sentinel-secret"

    backend_directory = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database; import conftest",
        ],
        cwd=backend_directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode != 0
    assert "Tests require a fresh Python process" in result.stderr
    assert not sentinel_database.exists()
