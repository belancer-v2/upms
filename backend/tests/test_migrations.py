"""The Alembic baseline must build exactly the schema the models describe, on an empty database.

If this fails after you changed a model, add a migration:  alembic revision --autogenerate -m "what changed"
(see backend/MIGRATIONS.md). Uses a private SQLite file; never touches the test database.
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models  # noqa: F401
from app.db import Base

BACKEND = Path(__file__).resolve().parent.parent


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path}/mig.db"
    command.upgrade(_cfg(url), "head")
    return url


def test_single_head():
    assert len(ScriptDirectory.from_config(_cfg("sqlite://")).get_heads()) == 1


def test_upgrade_matches_models(migrated):
    eng = create_engine(migrated)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": False}), Base.metadata)
    assert diff == [], f"models and migrations differ, add a migration: {diff[:5]}"
    names = set(inspect(eng).get_table_names()) - {"alembic_version"}
    assert names == set(Base.metadata.tables)


def test_downgrade_to_base(migrated):
    command.downgrade(_cfg(migrated), "base")
    assert set(inspect(create_engine(migrated)).get_table_names()) <= {"alembic_version"}


@pytest.mark.parametrize("dialect", [mysql.dialect(), postgresql.dialect()], ids=["mysql", "postgresql"])
def test_ddl_compiles_on_other_databases(dialect):
    """No server needed: every table and index must render for MySQL/MariaDB and PostgreSQL."""
    for t in Base.metadata.sorted_tables:
        ddl = str(CreateTable(t).compile(dialect=dialect))
        if dialect.name == "mysql":
            assert "DATETIME(6)" in ddl or "DATETIME" not in ddl
        for ix in t.indexes:
            str(CreateIndex(ix).compile(dialect=dialect))


def test_mysql_key_lengths_fit():
    """InnoDB keys are limited to 3072 bytes (utf8mb4 = 4 bytes per character)."""
    for t in Base.metadata.sorted_tables:
        keys = [list(ix.columns) for ix in t.indexes] + [list(c.columns) for c in t.constraints if c.__class__.__name__ in ("UniqueConstraint", "PrimaryKeyConstraint")]
        for cols in keys:
            size = sum((getattr(c.type, "length", None) or 8) * (4 if hasattr(c.type, "length") else 1) for c in cols)
            assert size <= 3072, f"{t.name} key {[c.name for c in cols]} is {size} bytes"
