# Database migrations

Alembic manages the schema. The API does not create or migrate tables at startup.
Run migrations before starting a new application version.

## Applying migrations

Install `backend/requirements.txt` and set `DATABASE_URL`. Alembic reads the root
`.env`; exported environment variables take precedence. It accepts
`postgresql+asyncpg://`, `postgresql://`, and `postgres://` URLs and does not require
`JWT_SECRET`. See [deployment](deployment.md#database-neon-postgresql) for Neon
connection settings.

For an empty database or one already managed by Alembic, run from `backend/`:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

`upgrade head` applies pending revisions and does nothing when already current.
`check` compares the schema with the models, but does not validate all constraints,
database objects, or stored data. If ApplyVault tables exist without an Alembic
revision, follow the adoption procedure below before upgrading.

## Adopting an existing database

Stamping records a revision without creating or repairing tables. Only stamp
`0001` after confirming that the existing schema matches the
[initial revision](../backend/migrations/versions/0001_initial_schema.py).

1. Pause application writes and take a full backup with `pg_dump --format=custom`.
   Restore it into a separate disposable database with `pg_restore` and verify row counts
   and representative records. Use `postgresql://` URLs, without `+asyncpg`, for
   these tools. Keep the backup outside Git; it contains private data and password
   hashes. Retain the previous application version until adoption is verified.
2. Point `DATABASE_URL` at the restored copy. From `backend/`, run
   `python -m alembic current`. If a revision is already recorded, investigate its
   migration history instead of overwriting it. Compare tables, primary and
   foreign keys, indexes, column lengths, and nullability with revision `0001`.
   Reconcile differences on the copy before proceeding; do not drop existing
   tables to make the initial migration pass.
3. On the matching copy, run:

   ```bash
   python -m alembic stamp 0001
   python -m alembic check
   python -m alembic upgrade head
   ```

   Stop if `check` reports differences. If later revisions exist, perform the
   baseline comparison and check using the code for `0001`, then switch to the
   release code and upgrade. A passing check does not replace the constraint
   comparison in step 2.
4. Verify row counts and records again. Test an existing login, application
   creation, editing and deletion, and new account creation to check ID sequences.
5. Keep writes paused and confirm the original database still matches the
   verified backup. Double-check the target host and database, then repeat the
   verified stamp, check, and upgrade sequence on the original. Run
   `python -m alembic current` and recheck data before restarting the API and
   resuming writes. Stop and investigate any discrepancy using the retained backup.

## Creating schema changes

After editing the models, use a migrated development database. From `backend/`:

```bash
python -m alembic revision --autogenerate -m "describe the schema change"
```

Review the generated revision before applying it. Autogeneration cannot infer all
renames or data transformations. Keep committed revisions immutable and add a new
revision for each change. Then run:

```bash
python -m alembic upgrade head
python -m alembic check
```

Run the [PostgreSQL integration tests](../README.md#tests) and back up the deployed
database before applying schema changes there.

The initial `downgrade base` drops both tables and all their rows. Use it only on
disposable databases. For a database whose data must survive, use a tested backup
restoration or a forward repair.
