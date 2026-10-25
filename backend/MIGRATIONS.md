# Database migrations (Alembic)

Production schema comes **only** from Alembic. With `ENV=production` the API does not call `create_all`.
Development and tests keep `create_all` (fast, throw-away databases).

Works on SQLite (dev/tests), MySQL/MariaDB 10.5+ (cPanel) and PostgreSQL 14+. The URL is `DATABASE_URL` (see `.env.example`);
`alembic.ini` has no URL. Run every command from `backend/` with the virtualenv active.

| Task | Command |
|---|---|
| Apply everything pending | `alembic upgrade head` |
| First install (migrate + reference data + first SUPER_ADMIN) | `python -m app.bootstrap` |
| Where is the database now? | `alembic current` |
| History | `alembic history --verbose` |
| Create a migration after changing a model | `alembic revision --autogenerate -m "add x to y"` then **read and edit the file** |
| Roll back one step | `alembic downgrade -1` |
| Show the SQL without running it (give to a DBA) | `alembic upgrade head --sql > upgrade.sql` |
| Mark an existing database as already at the baseline | `alembic stamp 0001` |

## Rules for writing a migration
1. Autogenerate is a draft. Check types, names, and that it does not drop data. It never detects renamed columns (it shows drop + add: write `op.alter_column(..., new_column_name=...)` by hand).
2. Money and counters that can pass 2 147 483 647 are `BigInteger` (paisa). Never `Float`.
3. Strings need an explicit length. Indexed/unique strings must stay under 191 characters on old MySQL, 3072 bytes total per key on MariaDB 10.5+ with utf8mb4 (`tests/test_migrations.py` checks this).
4. Do not use PostgreSQL-only or MySQL-only types or SQL. JSON uses `sa.JSON` (LONGTEXT with a JSON check on MariaDB).
5. New NOT NULL column on a table with rows: add it with a `server_default`, backfill, then (if you want) drop the default.
6. SQLite cannot ALTER most things; `env.py` renders SQLite changes in batch mode automatically. Write `with op.batch_alter_table(...)` for hand-written alters.
7. Every deploy: back up (`scripts/backup.sh`), `alembic upgrade head`, then start the new code. Backward-compatible steps (add column, then deploy code, then drop old column in a later release) make rollbacks safe.
8. `tests/test_migrations.py` fails if the models and the migrations disagree. That is the signal to add a migration.

## Baseline
`alembic/versions/…_0001_baseline.py` creates the whole schema as of the P1 hardening. Until the first production database exists,
the baseline may be regenerated instead of adding migrations on top of it:

```bash
rm alembic/versions/*_0001_baseline.py
ALEMBIC_BATCH=0 DATABASE_URL=sqlite:////tmp/empty.db alembic revision --autogenerate -m baseline --rev-id 0001
```
(`ALEMBIC_BATCH=0` renders plain operations instead of SQLite batch blocks.) After the first production install, **never** edit or regenerate it: add new revisions.

Indexes beyond those on the columns live in `app/models/indexes.py` (composite hot-filter indexes and a safety net that indexes every foreign key). Changing that file needs a migration too.

## Running the test suite on another database
```bash
docker compose -f docker-compose.test.yml up -d --wait          # PostgreSQL 16 on :55432 (add --profile mariadb for MariaDB on :53306)
cd backend
TEST_DATABASE_URL=postgresql://flatwise:flatwise@127.0.0.1:55432/flatwise_test python -m pytest -q
TEST_DATABASE_URL='mysql://root:flatwise@127.0.0.1:53306/flatwise_test' python -m pytest -q
```
The test run wipes that database. CI runs SQLite, PostgreSQL and MariaDB.

## Notes per database
* **MySQL/MariaDB**: `mysql://` is rewritten to `mysql+pymysql://…?charset=utf8mb4`. Create the database with `CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` (Bangla text). DATETIME columns are created as `DATETIME(6)`; MySQL has no time zone type, the app stores UTC. The collation is case-insensitive, which is what we want for e-mail addresses.
* **PostgreSQL**: `postgresql://` is rewritten to `postgresql+psycopg://`.
* **Uploads and encryption** are not in the database dump: back up `UPLOAD_DIR` and keep `NID_KEY` safe (see docs/RUNBOOK.md).
