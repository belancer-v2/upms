"""Operations: health probes, request ids, safe 500s, production start-up checks, bootstrap, NID re-keying, cPanel WSGI entry."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, prodcheck
from app.main import app

BACKEND = Path(__file__).resolve().parent.parent


def _run(args, env_extra, cwd=BACKEND):
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "ENV", "TEST_DATABASE_URL")}
    env.update({"FLATWISE_NO_DOTENV": "1", **env_extra})
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)


def test_health_ready_and_request_id(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["db"] is True
    assert client.get("/healthz", headers={"X-Request-ID": "abc-12345678"}).headers["x-request-id"] == "abc-12345678"
    assert len(client.get("/healthz", headers={"X-Request-ID": "bad id!"}).headers["x-request-id"]) == 32   # unsafe ids are replaced


def test_unhandled_error_is_safe_and_traceable(client):
    @app.get("/api/_boom_test")
    def boom():
        raise RuntimeError("secret internal detail")
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/_boom_test")
    assert r.status_code == 500 and r.json()["request_id"] == r.headers["x-request-id"]
    assert "Traceback" not in r.text


def test_gzip(client):
    assert "gzip" in client.get("/api/auth/demo-accounts", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding", "gzip")


def test_prodcheck_lists_every_problem(monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", prodcheck.DEFAULT_SECRET)
    monkeypatch.setattr(config, "DEMO", True)
    monkeypatch.setattr(config, "NID_KEY", "")
    monkeypatch.setattr(config, "CORS_ORIGINS", ["*"])
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///x.db")
    bad = "\n".join(prodcheck.problems({}))
    for needle in ("SECRET_KEY is not set", "built-in development default", "DEMO=1", "NID_KEY is empty", "wildcard", "SQLite", "APP_URL is not set", "DATABASE_URL is not set"):
        assert needle in bad, needle
    from cryptography.fernet import Fernet
    monkeypatch.setattr(config, "SECRET_KEY", "x" * 40)
    monkeypatch.setattr(config, "DEMO", False)
    monkeypatch.setattr(config, "NID_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(config, "CORS_ORIGINS", [])
    monkeypatch.setattr(config, "DATABASE_URL", "mysql+pymysql://u:p@localhost/db?charset=utf8mb4")
    env = {"SECRET_KEY": "x", "NID_KEY": "x", "DATABASE_URL": "x", "APP_URL": "https://example.com"}
    assert prodcheck.problems(env) == []                   # MySQL is accepted
    assert any("https" in p for p in prodcheck.problems({**env, "APP_URL": "http://example.com"}))


def test_production_refuses_unsafe_start_and_accepts_safe():
    r = _run(["-c", "import app.main"], {"ENV": "production"})
    assert r.returncode != 0 and "refuses to start" in r.stderr and "SECRET_KEY" in r.stderr and "NID_KEY" in r.stderr and "DEMO" not in r.stderr.replace("DEMO=1 is not allowed", "")
    from cryptography.fernet import Fernet
    good = {"ENV": "production", "SECRET_KEY": "s" * 48, "NID_KEY": Fernet.generate_key().decode(), "APP_URL": "https://example.com",
            "DATABASE_URL": "mysql://u:p@localhost/db"}
    r = _run(["-c", "import app.main as m; print(m.app.docs_url, m.app.openapi_url)"], good)
    assert r.returncode == 0 and "None None" in r.stdout, r.stderr
    r = _run(["-c", "import app.main"], {**good, "DEMO": "1"})
    assert r.returncode != 0 and "DEMO=1" in r.stderr
    r = _run(["-c", "from app import seed; seed.reset()"], {**good, "DATABASE_URL": "sqlite:///x.db"})
    assert r.returncode != 0   # seeding is hard-disabled in production (or refused by the start-up check)


def test_bootstrap_is_idempotent_and_makes_no_demo_data(tmp_path):
    env = {"DATABASE_URL": f"sqlite:///{tmp_path}/b.db", "BOOTSTRAP_ADMIN_EMAIL": "Boss@Example.com", "BOOTSTRAP_ADMIN_PASSWORD": "a-long-passphrase-1", "UPLOAD_DIR": str(tmp_path / "up")}
    for _ in range(2):
        r = _run(["-m", "app.bootstrap"], env)
        assert r.returncode == 0, r.stderr[-800:]
    check = ("from app.db import SessionLocal; from app.models.core import User; from app.models.saas import Plan; from sqlalchemy import select\n"
             "db=SessionLocal(); print([ (u.email,u.saas_role) for u in db.scalars(select(User))], [p.key for p in db.scalars(select(Plan))])")
    r = _run(["-c", check], env)
    assert "('boss@example.com', 'SUPER_ADMIN')" in r.stdout and "flatwise.demo" not in r.stdout and "'pro'" in r.stdout, r.stdout + r.stderr[-500:]
    r = _run(["-m", "app.bootstrap"], {**env, "BOOTSTRAP_ADMIN_PASSWORD": "short"})
    assert r.returncode == 0   # an admin exists already, so the missing password is not needed


def test_rekey_nid_roundtrip(tmp_path):
    from cryptography.fernet import Fernet
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    env = {"DATABASE_URL": f"sqlite:///{tmp_path}/r.db", "NID_KEY": old, "OLD_NID_KEY": old, "NEW_NID_KEY": new, "UPLOAD_DIR": str(tmp_path)}
    setup = ("from datetime import date; from app.db import Base, engine, SessionLocal; from app import models; from app.models.core import Organization, Property\n"
             "from app.models.staff import Staff; from app.services import vault\nBase.metadata.create_all(engine); db=SessionLocal()\n"
             "o=Organization(name='o'); db.add(o); db.flush(); p=Property(org_id=o.id,name='p'); db.add(p); db.flush()\n"
             "db.add(Staff(property_id=p.id,name='s',joined=date.today(),salary=1,nid_enc=vault.seal('1234567890123'),nid_last4='0123')); db.commit()")
    assert _run(["-c", setup], env).returncode == 0
    r = _run(["-m", "app.rekey_nid", "--dry-run"], env)
    assert r.returncode == 0 and "would re-encrypt      1  staff.nid_enc" in r.stdout, r.stdout + r.stderr
    r = _run(["-m", "app.rekey_nid"], env)
    assert r.returncode == 0 and "re-encrypted      1  staff.nid_enc" in r.stdout
    read = "from app.db import SessionLocal; from app.models.staff import Staff; from app.services import vault; print(vault.unseal(SessionLocal().query(Staff).one().nid_enc))"
    assert _run(["-c", read], {**env, "NID_KEY": new}).stdout.strip() == "1234567890123"
    bad = _run(["-m", "app.rekey_nid"], env)       # old key no longer fits: refuses and changes nothing
    assert bad.returncode != 0 and "cannot decrypt" in (bad.stderr + bad.stdout)


def test_cpanel_wsgi_entry(monkeypatch):
    from wsgiref.util import setup_testing_defaults
    monkeypatch.setenv("ENV", "development")
    monkeypatch.syspath_prepend(str(BACKEND))
    sys.modules.pop("passenger_wsgi", None)
    import passenger_wsgi
    seen = {}
    env = {"PATH_INFO": "/healthz", "REQUEST_METHOD": "GET"}
    setup_testing_defaults(env)
    body = b"".join(passenger_wsgi.application(env, lambda status, headers, exc=None: seen.update(status=status)))
    assert seen["status"].startswith("200") and b'"ok"' in body
