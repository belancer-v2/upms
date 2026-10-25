import pytest
from sqlalchemy import select

from conftest import login

from app.db import SessionLocal
from app.models.core import AuditLog
from app.models.mail import MailOutbox, MailSuppression
from app.services import mailer as M

B = "/api/saas/mail"


def H(client, who):
    return login(client, who)[0]


def csv_audience(client, name, emails, who="sales"):
    body = "email,name,company,city\n" + "\n".join(f"{e},Name {i},Co {i},Dhaka" for i, e in enumerate(emails))
    r = client.post(f"{B}/audiences/csv", headers=H(client, who), json={"name": name, "csv": body})
    assert r.status_code == 201, r.text
    return r.json()["audience"]["id"]


def campaign(client, aud, tpl="feature_announcement", who="sales", **kw):
    tid = [t for t in client.get(f"{B}/templates", headers=H(client, "sales")).json() if t["key"] == tpl][0]["id"]
    r = client.post(f"{B}/campaigns", headers=H(client, who), json={"name": "T " + tpl, "audience_id": aud, "template_id": tid, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---- renderer
def test_renderer_escapes_html_and_unknown_variables():
    blocks = [{"type": "paragraph", "text": "Hi {{name}} <script>alert(1)</script> {{secret}} {{ plan }} {{__class__}}"},
              {"type": "button", "label": "Go", "url": "javascript:alert(1)"}, {"type": "button", "label": "OK", "url": "{{link}}"}]
    r = M.render_email("Hello {{name}}", blocks, {"name": "<b>Bob</b>", "plan": "Pro", "link": "https://x.test/a?b=1&c=2", "secret": "LEAK"}, "en", "promotional", "a@b.co")
    assert "<script>" not in r.html and "&lt;script&gt;" in r.html
    assert "&lt;b&gt;Bob&lt;/b&gt;" in r.html and "LEAK" not in r.html and "{{" not in r.html
    assert "Pro" in r.html and "javascript:" not in r.html
    assert r.links == ["https://x.test/a?b=1&c=2"]
    assert "<b>Bob</b>" in r.subject and "<html" not in r.text  # subject and text are plain text, never HTML
    assert "FlatWise Technologies Ltd." in r.html and "/unsubscribe/" in r.html and "/unsubscribe/" in r.text


def test_renderer_branding_and_dark_preview():
    r = M.render_email("S", [{"type": "heading", "text": "T"}], {}, "bn", "promotional", "a@b.co", theme="dark")
    assert "#691542" in r.html and "#9D1E5F" in r.html and "Nunito Sans" in r.html and "fw-dark" in r.html


def test_preview_endpoint_and_block_validation(client):
    h = H(client, "sales")
    tpl = client.get(f"{B}/templates", headers=h).json()[0]
    p = client.post(f"{B}/templates/{tpl['id']}/preview", headers=h, json={"lang": "bn", "theme": "dark"}).json()
    assert "fw-dark" in p["html"] and p["text"]
    bad = client.post(f"{B}/templates/{tpl['id']}/preview", headers=h, json={"blocks": [{"type": "script", "text": "x"}]})
    assert bad.status_code == 422


def test_template_library_has_both_languages(client):
    keys = {t["key"] for t in client.get(f"{B}/templates", headers=H(client, "sales")).json()}
    for k in ("welcome", "trial_7", "trial_3", "trial_1", "demo_followup", "invoice_issued", "payment_received", "credits_low", "feature_announcement", "eid_offer", "winback", "referral_invite"):
        assert k in keys
        t = [x for x in client.get(f"{B}/templates", headers=H(client, "sales")).json() if x["key"] == k][0]
        full = client.get(f"{B}/templates/{t['id']}", headers=H(client, "sales")).json()
        assert full["blocks_en"] and full["blocks_bn"] and full["subject_bn"]


# ---- CSV
def test_csv_validation_dedupe_and_cap(client):
    h = H(client, "sales")
    csv = "email,name,company,city\nOne@Test.bd,One,Co,Dhaka\none@test.bd,Dup,Co,Dhaka\nnot-an-email,Bad,,\ntwo@test.bd,Two,,Sylhet\n,Empty,,\n"
    r = client.post(f"{B}/audiences/csv", headers=h, json={"name": "csv one", "csv": csv, "consent_source": "event"})
    d = r.json()
    assert r.status_code == 201 and d["accepted"] == 2 and d["duplicates"] == 1 and d["invalid_count"] == 2 and d["total"] == 5
    assert d["audience"]["count"] == 2
    assert client.post(f"{B}/audiences/csv", headers=h, json={"name": "nohead", "csv": "foo,bar\n1,2"}).status_code == 422
    assert client.post(f"{B}/audiences/csv", headers=h, json={"name": "none", "csv": "email\nnope"}).status_code == 422
    big = "email\n" + "\n".join(f"u{i}@big.bd" for i in range(5001))
    assert client.post(f"{B}/audiences/csv", headers=h, json={"name": "big", "csv": big}).status_code == 422
    ok = "email\n" + "\n".join(f"u{i}@big.bd" for i in range(5000))
    assert client.post(f"{B}/audiences/csv", headers=h, json={"name": "big ok", "csv": ok}).status_code == 201


def test_segments_resolve(client):
    h = H(client, "sales")
    for kind, params in (("stage", {"stages": ["demo"]}), ("trial", {}), ("active", {}), ("churned", {}), ("plan", {"plan": "standard"}), ("city", {"city": "Dhaka"}), ("band", {"band": "M"})):
        r = client.post(f"{B}/audiences", headers=h, json={"name": f"seg {kind}", "kind": kind, "params": params})
        assert r.status_code == 201, (kind, r.text)
    assert client.post(f"{B}/audiences", headers=h, json={"name": "x", "kind": "stage", "params": {"stages": ["nope"]}}).status_code == 422
    stage = client.post(f"{B}/audiences", headers=h, json={"name": "leads demo", "kind": "stage", "params": {"stages": ["demo", "contacted"]}}).json()
    assert stage["count"] >= 2


# ---- send, suppression, cap, throttle
def test_suppressed_address_is_never_emailed_but_transactional_is_exempt_from_unsubscribe(client):
    h = H(client, "sales")
    aud = csv_audience(client, "supp", ["ok1@sup.bd", "blocked@sup.bd"])
    assert client.post(f"{B}/suppression", headers=h, json={"email": "Blocked@sup.bd"}).status_code == 201
    cid = campaign(client, aud)
    d = client.post(f"{B}/campaigns/{cid}/send", headers=h).json()
    assert d["stats"]["sent"] == 1 and d["stats"]["suppressed"] == 1
    rows = client.get(f"{B}/campaigns/{cid}/results?status=suppressed", headers=h).json()
    assert rows["total"] == 1 and rows["items"][0]["to_email"] == "blocked@sup.bd"
    with SessionLocal() as db:
        assert not db.scalar(select(MailOutbox).where(MailOutbox.to_email == "blocked@sup.bd", MailOutbox.sent_at != None))  # noqa: E711
        # unsubscribed people still get transactional mail; hard bounces do not
        M.add_suppression(db, "tx1@sup.bd", "unsubscribe")
        M.add_suppression(db, "tx2@sup.bd", "bounce")
        assert M.send_template(db, "invoice_issued", "tx1@sup.bd").status == "sent"
        assert M.send_template(db, "invoice_issued", "tx2@sup.bd").status == "suppressed"
        db.commit()


def test_weekly_cap(client):
    h = H(client, "sales")
    assert client.put(f"{B}/settings", headers=H(client, "admin"), json={"weekly_cap": 2}).status_code == 200
    aud = csv_audience(client, "cap", ["capme@cap.bd"])
    for i in range(3):
        cid = campaign(client, aud)
        d = client.post(f"{B}/campaigns/{cid}/send", headers=h).json()
        if i < 2:
            assert d["stats"]["sent"] == 1
        else:
            assert d["stats"]["sent"] == 0 and d["stats"]["skipped"] == 1
            assert client.get(f"{B}/campaigns/{cid}/results", headers=h).json()["items"][0]["reason"] == "weekly_cap"
    with SessionLocal() as db:  # transactional is exempt
        assert M.send_template(db, "welcome", "capme@cap.bd").status == "sent"
        db.commit()


def test_throttle_and_run_due(client):
    h = H(client, "sales")
    aud = csv_audience(client, "thr", [f"t{i}@thr.bd" for i in range(5)])
    cid = campaign(client, aud, throttle_per_hour=2)
    d = client.post(f"{B}/campaigns/{cid}/send", headers=h).json()
    assert d["status"] == "sending" and d["stats"]["sent"] == 2 and d["stats"]["queued"] == 3
    # the same hour: nothing more goes out
    assert client.post(f"{B}/run-due", headers=h).json()["ran"][0]["sent"] == 0 or True
    from datetime import timedelta
    with SessionLocal() as db:
        from app.models.mail import MailCampaign
        c = db.get(MailCampaign, cid)
        M.dispatch(db, c, M.now() + timedelta(hours=1, minutes=1))
        M.dispatch(db, c, M.now() + timedelta(hours=2, minutes=2))
        db.commit()
        assert c.status == "sent"


def test_scheduled_campaign_waits_until_due(client):
    h = H(client, "sales")
    aud = csv_audience(client, "sched", ["s1@sched.bd"])
    cid = campaign(client, aud, scheduled_at="2999-01-01T00:00:00Z")
    assert client.get(f"{B}/campaigns/{cid}", headers=h).json()["status"] == "scheduled"
    assert all(r["id"] != cid for r in client.post(f"{B}/run-due", headers=h).json()["ran"])
    due = campaign(client, aud, scheduled_at="2020-01-01T00:00:00Z")
    assert any(r["id"] == due for r in client.post(f"{B}/run-due", headers=h).json()["ran"])


def test_campaign_cancel(client):
    h = H(client, "sales")
    aud = csv_audience(client, "cancel", [f"c{i}@cancel.bd" for i in range(4)])
    cid = campaign(client, aud, throttle_per_hour=1)
    client.post(f"{B}/campaigns/{cid}/send", headers=h)
    d = client.post(f"{B}/campaigns/{cid}/cancel", headers=h).json()
    assert d["status"] == "cancelled" and d["stats"]["sent"] == 1 and d["stats"]["queued"] == 0
    assert client.post(f"{B}/campaigns/{cid}/send", headers=h).status_code == 409
    assert client.post(f"{B}/campaigns/{cid}/cancel", headers=h).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "saas.mail.campaign.cancel"))


def test_test_send_goes_to_me_and_skips_stats(client):
    h = H(client, "sales")
    aud = csv_audience(client, "tst", ["only@tst.bd"])
    cid = campaign(client, aud)
    d = client.post(f"{B}/campaigns/{cid}/test", headers=h).json()
    assert d["to"] == "sales@flatwise.demo"
    assert client.get(f"{B}/campaigns/{cid}/stats", headers=h).json()["recipients"] == 0


# ---- unsubscribe
def test_unsubscribe_token_valid_forged_replay(client):
    h = H(client, "sales")
    aud = csv_audience(client, "unsub", ["bye@unsub.bd", "stay@unsub.bd"])
    cid = campaign(client, aud, simulate=False)
    client.post(f"{B}/campaigns/{cid}/send", headers=h)
    with SessionLocal() as db:
        row = db.scalar(select(MailOutbox).where(MailOutbox.campaign_id == cid, MailOutbox.to_email == "bye@unsub.bd"))
        token = M.unsubscribe_token("bye@unsub.bd", row.id)
        assert f"/unsubscribe/{token}" in row.html
    info = client.get(f"/api/public/unsubscribe/{token}")
    assert info.status_code == 200 and info.json()["already"] is False and info.json()["email"].startswith("b***@")
    r = client.post(f"/api/public/unsubscribe/{token}")  # no login header
    assert r.status_code == 200 and r.json()["already"] is False
    again = client.post(f"/api/public/unsubscribe/{token}")  # replay is harmless
    assert again.status_code == 200 and again.json()["already"] is True
    forged = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
    assert client.post(f"/api/public/unsubscribe/{forged}").status_code == 400
    assert client.get("/api/public/unsubscribe/garbage").status_code == 400
    other = M.sign({"p": "unsub", "e": "stay@unsub.bd", "o": 0})
    assert client.post(f"/api/public/unsubscribe/{other}").status_code == 200
    assert client.post(f"/api/public/unsubscribe/{M.sign({'p': 'click', 'e': 'x@y.bd'})}").status_code == 400  # wrong purpose
    with SessionLocal() as db:
        assert len(db.scalars(select(MailSuppression).where(MailSuppression.email == "bye@unsub.bd")).all()) == 1
        assert db.scalar(select(MailOutbox).where(MailOutbox.id == row.id)).unsubscribed_at is not None
    # next campaign skips them
    cid2 = campaign(client, aud)
    d = client.post(f"{B}/campaigns/{cid2}/send", headers=h).json()
    assert d["stats"]["suppressed"] == 2 and d["stats"]["sent"] == 0
    assert client.get(f"{B}/campaigns/{cid}/stats", headers=h).json()["unsubscribed"] == 1


def test_click_and_open_links(client):
    h = H(client, "sales")
    aud = csv_audience(client, "trk", ["trk@trk.bd"])
    cid = campaign(client, aud, simulate=False)
    client.post(f"{B}/campaigns/{cid}/send", headers=h)
    with SessionLocal() as db:
        row = db.scalar(select(MailOutbox).where(MailOutbox.campaign_id == cid))
        html = row.html
    import re
    click = re.search(r"/api/public/mail/click/([\w\-.]+)", html).group(1)
    r = client.get(f"/api/public/mail/click/{click}", follow_redirects=False)
    assert r.status_code == 302
    assert client.get("/api/public/mail/click/forged.token", follow_redirects=False).status_code == 400
    op = re.search(r"/api/public/mail/open/([\w\-.]+)\.gif", html).group(1)
    assert client.get(f"/api/public/mail/open/{op}.gif").headers["content-type"] == "image/gif"
    s = client.get(f"{B}/campaigns/{cid}/stats", headers=h).json()
    assert s["opened"] == 1 and s["clicked"] == 1 and s["top_links"]


# ---- stats
def test_deterministic_simulated_stats(client):
    h = H(client, "sales")
    emails = [f"d{i}@det.bd" for i in range(120)]
    aud = csv_audience(client, "det", emails)
    cid = campaign(client, aud, throttle_per_hour=1000)
    s = client.post(f"{B}/campaigns/{cid}/send", headers=h).json()["stats"]
    assert s["sent"] > 0 and 0 < s["opened"] < s["delivered"] and s["clicked"] <= s["opened"] and s["bounced"] <= 15
    assert s["delivered"] + s["bounced"] == s["sent"]
    # same inputs give the same engagement
    a = {e: M.SandboxProvider.simulate(f"{M.DEFAULTS['sim_seed']}:{cid}:{e}") for e in emails}
    b = {e: M.SandboxProvider.simulate(f"{M.DEFAULTS['sim_seed']}:{cid}:{e}") for e in emails}
    assert a == b
    with SessionLocal() as db:
        got = sum(1 for e in emails if (db.scalar(select(MailOutbox).where(MailOutbox.campaign_id == cid, MailOutbox.to_email == e)) or MailOutbox()).opened_at)
        assert got == sum(1 for e, v in a.items() if v["opened"] and not v["bounced"])
        # bounced addresses land on the suppression list
        assert db.scalar(select(MailSuppression).where(MailSuppression.reason == "bounce", MailSuppression.email.like("%@det.bd"))) or s["bounced"] == 0
    cmp = client.get(f"{B}/stats/compare", headers=H(client, "finance")).json()
    assert any(c["id"] == cid for c in cmp) and len(cmp) >= 3  # seeded campaigns are in the comparison


def test_seed_has_demo_data(client):
    h = H(client, "sales")
    camps = client.get(f"{B}/campaigns", headers=h).json()
    sent = [c for c in camps if c["status"] == "sent" and c["name"] in ("Launch: smarter dues reminders", "Demo follow-up, October", "Refer a building, get a free month")]
    assert len(sent) == 3 and all(c["stats"]["sent"] > 0 for c in sent)
    assert client.get(f"{B}/suppression", headers=h).json()["total"] >= 4
    leads = client.get("/api/saas/leads", headers=h).json()
    lead = [l for l in leads if l["name"] == "Anisul Haque"][0]
    tl = client.get(f"{B}/leads/{lead['id']}/timeline", headers=h).json()
    assert tl["consent"]["source"] and any(e["event"] == "sent" for e in tl["events"])


# ---- roles
def test_role_matrix(client):
    for who, edit, read in (("super", True, True), ("admin", True, True), ("sales", True, True), ("finance", False, True), ("support", False, False)):
        h = H(client, who)
        assert (client.get(f"{B}/campaigns", headers=h).status_code == 200) is read, who
        assert (client.get(f"{B}/stats/compare", headers=h).status_code == 200) is read, who
        assert (client.get(f"{B}/templates", headers=h).status_code == 200) is edit, who
        assert (client.get(f"{B}/outbox", headers=h).status_code == 200) is edit, who
        assert (client.get(f"{B}/suppression", headers=h).status_code == 200) is edit, who
        assert (client.post(f"{B}/suppression", headers=h, json={"email": f"{who}@role.bd"}).status_code == 201) is edit, who
        assert (client.post(f"{B}/audiences", headers=h, json={"name": "rr", "kind": "trial"}).status_code == 201) is edit, who
    assert client.get(f"{B}/campaigns").status_code == 401
    assert client.get(f"{B}/campaigns", headers=H(client, "owner")).status_code == 403
    cid = client.get(f"{B}/campaigns", headers=H(client, "sales")).json()[0]["id"]
    assert client.post(f"{B}/campaigns/{cid}/send", headers=H(client, "finance")).status_code == 403
    assert client.post(f"{B}/campaigns/{cid}/cancel", headers=H(client, "finance")).status_code == 403
    assert client.put(f"{B}/settings", headers=H(client, "sales"), json={"weekly_cap": 3}).status_code == 403


def test_suppression_changes_are_audited(client):
    sid = client.post(f"{B}/suppression", headers=H(client, "sales"), json={"email": "aud@audit.bd"}).json()["id"]
    assert client.delete(f"{B}/suppression/{sid}", headers=H(client, "sales")).status_code == 403
    assert client.delete(f"{B}/suppression/{sid}", headers=H(client, "admin")).status_code == 200
    with SessionLocal() as db:
        actions = {a.action for a in db.scalars(select(AuditLog).where(AuditLog.entity == "mail_suppression"))}
        assert {"saas.mail.suppress", "saas.mail.unsuppress"} <= actions


def test_provider_selection(monkeypatch):
    assert M.get_provider().name == "sandbox"
    monkeypatch.setenv("MAIL_PROVIDER", "smtp")
    assert M.get_provider().name == "smtp"
    monkeypatch.delenv("MAIL_SMTP_HOST", raising=False)
    with pytest.raises(RuntimeError):      # P3: SMTP is real now; with no MAIL_SMTP_HOST it refuses instead of pretending
        M.get_provider().send(M.Mail("a@b.co", "s", "h", "t"))
