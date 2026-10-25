import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping drops dead connections after a database restart; pool sizes only matter for PostgreSQL.
_mysql = DATABASE_URL.startswith("mysql")   # shared hosts allow few connections and close idle ones after ~5 minutes
_pool = {} if DATABASE_URL.startswith("sqlite") else {"pool_size": int(os.getenv("DB_POOL_SIZE", "3" if _mysql else "10")), "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "2" if _mysql else "10")),
                                                      "pool_recycle": 270 if _mysql else 1800}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, hide_parameters=True, **_pool)  # hide_parameters: error messages and logs never print bound values (hashes, tokens, NIDs)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # enforce foreign keys in SQLite like Postgres does
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# MySQL/MariaDB: plain DATETIME drops microseconds; the app relies on them for ordering and equality. Keep them.
from sqlalchemy import DateTime  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(DateTime, "mysql", "mariadb")
def _datetime_fsp(type_, compiler, **kw):
    return "DATETIME(6)"
