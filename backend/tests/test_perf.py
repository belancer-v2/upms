"""List endpoints must not run one query per row. Counts SQL statements with 200 extra rows and compares to the baseline."""
from datetime import date, timedelta
from secrets import token_hex

import pytest
from sqlalchemy import delete, event, select

from app.db import SessionLocal, engine
from app.models.billing import Invoice
from app.models.core import User, now
from app.models.notice import Notice, Receipt
from app.models.property import Unit
from app.models.requests import ServiceRequest
from app.models.staff import Staff
from test_property import prop_headers

N = 200


class Counter:
    def __enter__(self):
        self.n = 0
        event.listen(engine, "before_cursor_execute", self._hit)
        return self

    def __exit__(self, *a):
        event.remove(engine, "before_cursor_execute", self._hit)

    def _hit(self, *a, **k):
        self.n += 1


def _count(client, url, h):
    with Counter() as c:
        r = client.get(url, headers=h)
    assert r.status_code == 200, r.text
    return c.n, r.json()


@pytest.fixture()
def bulk(client):
    h = prop_headers(client, "padmin")
    pid = int(h["X-Property-Id"])
    ids = {"inv": [], "notice": [], "req": [], "staff": []}
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == "padmin@flatwise.demo"))
        unit = db.scalar(select(Unit).where(Unit.property_id == pid))
        base = {url: _count(client, url, h)[0] for url in ("/api/billing/invoices", "/api/notices", "/api/requests?size=100", "/api/staff")}
        day = date.today()
        for i in range(N):
            inv = Invoice(property_id=pid, unit_id=unit.id, period=f"9{i:03d}-01", number=f"PERF-{i}", issue_date=day, due_date=day + timedelta(days=10), total=100000, paid=0)
            n = Notice(property_id=pid, title=f"Perf notice {i}", body="x", created_by=uid)
            r = ServiceRequest(property_id=pid, unit_id=unit.id, raised_by=uid, category="other", title=f"Perf {i}", due_at=now() + timedelta(days=3))
            s = Staff(property_id=pid, name=f"Perf Staff {i}", joined=day, salary=100000)
            db.add_all([inv, n, r, s])
            db.flush()
            db.add(Receipt(notice_id=n.id, name="A", unit="A-1", token=token_hex(8), user_id=uid))
            ids["inv"].append(inv.id); ids["notice"].append(n.id); ids["req"].append(r.id); ids["staff"].append(s.id)
        db.commit()
    yield h, base
    with SessionLocal() as db:
        db.execute(delete(Receipt).where(Receipt.notice_id.in_(ids["notice"])))
        for model, key in ((Invoice, "inv"), (Notice, "notice"), (ServiceRequest, "req"), (Staff, "staff")):
            db.execute(delete(model).where(model.id.in_(ids[key])))
        db.commit()


@pytest.mark.parametrize("url,rows", [("/api/billing/invoices", N), ("/api/notices", 100), ("/api/requests?size=100", 100), ("/api/staff", N)])
def test_list_query_count_does_not_grow_with_rows(client, bulk, url, rows):
    h, base = bulk
    n, body = _count(client, url, h)
    items = body["items"] if isinstance(body, dict) else body
    assert len(items) >= min(rows, 100) - 5, f"{url} returned only {len(items)} rows"
    assert n <= base[url] + 2, f"{url}: {n} queries with {N} extra rows vs {base[url]} before (N+1?)"
    assert n <= 30
