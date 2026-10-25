"""Alembic environment. The database URL comes from app.config.DATABASE_URL (env var DATABASE_URL),
never from alembic.ini. Tests may override it with config.set_main_option("sqlalchemy.url", ...)."""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import config as app_config
from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.db import Base
from app.models import indexes

indexes.attach()  # models imported late are covered too

cfg = context.config
if cfg.config_file_name is not None:
    fileConfig(cfg.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return cfg.get_main_option("sqlalchemy.url") or app_config.DATABASE_URL


def _opts(url: str) -> dict:
    return dict(target_metadata=target_metadata, compare_type=True, compare_server_default=False,
                # SQLite cannot ALTER most things in place, so its migrations are rendered in batch mode.
                # ALEMBIC_BATCH=0 renders plain operations (used to write the baseline).
                render_as_batch=url.startswith("sqlite") and os.getenv("ALEMBIC_BATCH", "1") != "0")


def run_migrations_offline() -> None:
    url = _url()
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"}, **_opts(url))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    with engine.connect() as connection:
        context.configure(connection=connection, **_opts(url))
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
