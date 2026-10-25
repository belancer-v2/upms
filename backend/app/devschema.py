"""Development convenience: adds columns that were introduced after a local database was created (create_all never alters tables).

Production uses Alembic only (see alembic/versions/*_security_hardening.py); this is never called when ENV=production.
"""
from sqlalchemy import inspect, text

COLUMNS = {
    "users": [("token_version", "INTEGER NOT NULL DEFAULT 0"), ("must_change_password", "BOOLEAN NOT NULL DEFAULT 0"),
              ("password_changed_at", "TIMESTAMP NULL"), ("email_verified", "BOOLEAN NOT NULL DEFAULT 1")],
    "audit_log": [("prev_hash", "VARCHAR(64) NOT NULL DEFAULT ''"), ("row_hash", "VARCHAR(64) NOT NULL DEFAULT ''")],
}


def ensure_columns(engine) -> None:
    insp = inspect(engine)
    with engine.begin() as c:
        for table, cols in COLUMNS.items():
            if table not in insp.get_table_names():
                continue
            have = {x["name"] for x in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    ddl2 = ddl.replace("DEFAULT 0", "DEFAULT false").replace("DEFAULT 1", "DEFAULT true") if engine.dialect.name == "postgresql" and "BOOLEAN" in ddl else ddl
                    c.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl2}"))
