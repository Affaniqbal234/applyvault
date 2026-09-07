# Database migrations

Alembic applies schema changes. The API does not create tables at startup. Run
migrations once per release, before starting the API workers. The web process in
`backend/Procfile` only starts Uvicorn; configure your host's pre-deploy command or
run the migration as a separate release step.

## New databases

Create an empty PostgreSQL database, install `backend/requirements.txt`, and set
`DATABASE_URL`. Alembic reads the repository root `.env`, with exported environment
variables taking precedence. It accepts `postgresql+asyncpg://`, `postgresql://`,
and `postgres://` URLs. It does not need `JWT_SECRET`.

From `backend/`:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
uvicorn main:app --reload
```

Revision `0001` matches the previous SQLAlchemy `create_all()` schema: both tables,
primary keys, column lengths and nullability, the unique email index, and the
application ownership foreign key and index. Passwords, application rows, and IDs
are not transformed. SQLAlchemy supplies status and timestamp defaults when it
inserts rows; the baseline does not add database defaults. Direct SQL
inserts must supply required values.

`upgrade head` on an already current database does not repeat the migration.
`alembic check` compares the migrated schema with the models, including column
types and server defaults. It is useful evidence of alignment, but it does not
validate every database object, row, trigger, or privilege.

## Adopting an existing database

Do not run the initial upgrade on a database that already contains ApplyVault
tables. Do not blindly stamp `head`: stamping records a version without creating
or repairing the schema.

1. Pause application writes and take a full backup. Keep the previous application
   version available. Use PostgreSQL CLI URLs (`postgresql://`, without
   `+asyncpg`) for `pg_dump` and `pg_restore`. Record the user/application counts
   and representative rows, including IDs, password hashes, notes, and timestamps.
2. Restore the backup into a new, disposable database. Check that restoration
   succeeded and the counts and sampled rows match. Keep the original untouched
   during this rehearsal. With `SOURCE_PG_URL` and `REHEARSAL_PG_URL` explicitly
   set to the original and an empty rehearsal database, these commands create and
   restore a custom-format backup:

   ```bash
   pg_dump --dbname="$SOURCE_PG_URL" --format=custom --file=applyvault-before-alembic.dump
   pg_restore --dbname="$REHEARSAL_PG_URL" --no-owner --no-privileges --exit-on-error applyvault-before-alembic.dump
   ```

   Keep the backup outside Git: it contains private application data and password
   hashes. In PowerShell, environment variables use `$env:SOURCE_PG_URL` and
   `$env:REHEARSAL_PG_URL`.

3. Use this milestone's baseline code for the schema comparison. Point
   `DATABASE_URL` at the **rehearsal** database and run from `backend/`:

   ```bash
   python -m alembic current
   python -m alembic stamp 0001
   python -m alembic check
   ```

   Before stamping, `current` should show no revision. If a version is already
   recorded, investigate that migration history instead of replacing it. If
   `check` reports differences, stop: stamping has not fixed them. Compare the
   database with `backend/migrations/versions/0001_initial_schema.py`, including
   primary keys, foreign keys, indexes, lengths, and nullability. Reconcile any
   differences on the copy, repeat the rehearsal, and plan the corresponding
   changes for the original database. Never delete existing tables to make the
   initial migration pass. Even when `check` passes, verify the primary keys and
   other constraints against the initial revision; Alembic does not detect every
   kind of difference.

4. On the verified copy, run `python -m alembic upgrade head`, then check the counts
   and sampled rows again. Test login with an existing account and create, update,
   and delete an application. Also create a new account to verify ID sequences.
5. Once the copy passes, confirm the original still matches the backup and has
   no schema drift. Keep writes paused. Point `DATABASE_URL` at the original,
   double-check the host and database name, and run `stamp 0001`, `check`,
   `upgrade head`, and `current` there. Recheck data before starting the API and
   resuming writes. If anything differs, stop and diagnose using the retained
   backup and rehearsal results.

For a later release, establish this baseline using the code that defines `0001`
first, then apply subsequent revisions in order. Partially created tables or a
different legacy schema need reconciliation before adoption; there is no safe
generic stamp command that repairs them.

## Changing the schema later

After editing the models, use a migrated development database:

```bash
python -m alembic revision --autogenerate -m "describe the schema change"
python -m alembic upgrade head
python -m alembic check
```

Review the generated revision before applying it. Autogeneration cannot infer
all renames or required data transformations. Keep committed revisions immutable
and add a new revision for each later change.

The initial `downgrade base` drops both tables and all their rows. It exists for
disposable tests and is not a data-preserving rollback for an adopted database.
Use a tested backup restoration or a forward repair when data must survive.

## Disposable PostgreSQL checks

The `integration_tests/` suite is outside `backend/` so it does not share the
SQLite harness's imports or database configuration. It initializes a fresh cluster
with `initdb`, uses a generated password, binds a random loopback port, creates
one database per test, and stops its own server during teardown. It never targets
an inherited `DATABASE_URL`, `PGHOST`, or `PGDATA`. Run it as a normal user, not
root. PostgreSQL refuses to initialize a cluster as root.

Install `backend/requirements-dev.txt` and PostgreSQL binaries. Set `POSTGRES_BIN` if the
binaries are not on `PATH`. Example for Windows PowerShell:

```powershell
$env:POSTGRES_BIN = 'C:\Program Files\PostgreSQL\18\bin'
python -m pytest integration_tests/ -q
```

On Linux, for a PostgreSQL 16 installation:

```bash
POSTGRES_BIN=/usr/lib/postgresql/16/bin python -m pytest integration_tests/ -q
```

The tests cover empty-database upgrades, schema/model alignment, repeated upgrades
with stored rows, downgrade/re-upgrade, uniqueness and ownership constraints,
column nullability and lengths, backup/restore and legacy adoption, schema drift,
sentinel-database isolation, startup without schema changes, and an API flow
against the migrated database. PostgreSQL binaries are
required; a missing installation fails rather than skips this suite.

References: [Alembic's async migration recipe](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic),
[Alembic commands and stamping](https://alembic.sqlalchemy.org/en/latest/api/commands.html#alembic.command.stamp).
