import os
import tempfile

_tmp = tempfile.mkdtemp()
# TEST_DATABASE_URL=postgresql://... runs the whole suite on PostgreSQL (see backend/MIGRATIONS.md and docker-compose.test.yml)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ.pop("ENV", None)  # tests always run as development
os.environ["FLATWISE_NO_DOTENV"] = "1"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"

import pytest
from fastapi.testclient import TestClient

from app import seed
from app.main import app


@pytest.fixture(scope="session")
def client():
    seed.run()
    with TestClient(app) as c:
        yield c


def login(client, who, pw="demo1234"):
    r = client.post("/api/auth/login", json={"email": f"{who}@flatwise.demo", "password": pw})
    assert r.status_code == 200, r.text
    data = r.json()
    if data.get("must_change_password"):   # first sign-in with a temporary password: finish the forced change the way a person would
        ch = client.post("/api/auth/change-password", headers={"Authorization": f"Bearer {data['token']}"}, json={"current_password": pw, "new_password": "Fresh-Pass#2026"})
        assert ch.status_code == 200, ch.text
        data = {**data, **ch.json()}
    return {"Authorization": f"Bearer {data['token']}"}, data


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate limits and lockouts are stored in the database; every test starts with a clean slate (P2 security)."""
    from app.services import ratelimit
    ratelimit.reset_all()
    yield
