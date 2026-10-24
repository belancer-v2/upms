import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

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
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()
