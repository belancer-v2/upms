import base64
import datetime as dt
import json
import smtplib

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import select

from app.db import SessionLocal
from app.models.mail import MailOutbox, MailSuppression
from app.routers import webhooks
from app.services import mail_transport as T
from app.services import mailer as M


class FakeSmtp:
    log = []
    fail_times = 0
    code = 421

    def __init__(self, host, port, timeout):
        self.sent = None
        FakeSmtp.log.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSmtp.log.append(("starttls",))

    def login(self, u, p):
        FakeSmtp.log.append(("login", u))

    def send_message(self, m):
        if FakeSmtp.fail_times > 0:
            FakeSmtp.fail_times -= 1
            raise smtplib.SMTPResponseException(FakeSmtp.code, b"try later" if FakeSmtp.code < 500 else b"no such user")
        FakeSmtp.log.append(("msg", m))


@pytest.fixture
def smtp(monkeypatch):
    FakeSmtp.log, FakeSmtp.fail_times, FakeSmtp.code = [], 0, 421
    for k, v in {"MAIL_SMTP_HOST": "smtp.example.test", "MAIL_SMTP_USER": "u", "MAIL_SMTP_PASSWORD": "pw-secret-1", "MAIL_FROM": "FlatWise <hello@flatwise.test>", "MAIL_SMTP_RETRIES": "2"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(M.SmtpProvider, "transport_factory", FakeSmtp)
    monkeypatch.setattr(T.time, "sleep", lambda s: None)
    return FakeSmtp


def mail():
    return M.Mail("a@b.test", "Hi", "<p>Hi</p>", "Hi", "https://app.test/unsubscribe/tok")


def test_smtp_sends_with_tls_login_and_unsubscribe_headers(smtp):
    mid = M.SmtpProvider().send(mail())
    assert mid.startswith("<") and [x[0] for x in smtp.log] == ["connect", "starttls", "login", "msg"]
    m = smtp.log[-1][1]
    assert m["To"] == "a@b.test" and m["List-Unsubscribe"] == "<https://app.test/unsubscribe/tok>" and m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert m.get_body(("html",)).get_content().strip() == "<p>Hi</p>" and m.get_body(("plain",)).get_content().strip() == "Hi"


def test_smtp_retries_temporary_errors_but_not_permanent(smtp):
    smtp.fail_times = 2
    M.SmtpProvider().send(mail())
    assert [x[0] for x in smtp.log].count("msg") == 1
    smtp.log.clear()
    smtp.fail_times, smtp.code = 5, 550
    with pytest.raises(RuntimeError) as e:
        M.SmtpProvider().send(mail())
    assert "550" in str(e.value) and [x[0] for x in smtp.log].count("connect") == 1 and "pw-secret-1" not in str(e.value)


def test_smtp_gives_up_after_retries(smtp):
    smtp.fail_times = 10
    with pytest.raises(RuntimeError) as e:
        M.SmtpProvider().send(mail())
    assert "unreachable" in str(e.value) and [x[0] for x in smtp.log].count("connect") == 3


def test_smtp_config_errors(monkeypatch):
    monkeypatch.delenv("MAIL_SMTP_HOST", raising=False)
    monkeypatch.delenv("SES_REGION", raising=False)
    with pytest.raises(RuntimeError):
        M.SmtpProvider().send(mail())


def test_ses_uses_regional_smtp_host_and_configuration_set(smtp, monkeypatch):
    monkeypatch.delenv("MAIL_SMTP_HOST")
    monkeypatch.setenv("SES_REGION", "ap-southeast-1")
    monkeypatch.setenv("SES_CONFIGURATION_SET", "fw-events")
    M.SesProvider().send(mail())
    assert smtp.log[0] == ("connect", "email-smtp.ap-southeast-1.amazonaws.com", 587) and smtp.log[-1][1]["X-SES-CONFIGURATION-SET"] == "fw-events"


def test_provider_failure_marks_outbox_failed_not_crash(client, smtp, monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "smtp")
    smtp.fail_times, smtp.code = 5, 550
    with SessionLocal() as db:
        row = M.send_template(db, "welcome", "newperson@example.test", "N", "en", {"building": "B"})
        db.commit()
        assert row.status == "failed" and row.provider == "smtp"


# ---------------------------------------------------------------- SES / SNS
def make_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(dt.datetime(2020, 1, 1)).not_valid_after(dt.datetime(2040, 1, 1)).sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM)


KEY, PEM = make_cert()
CERT_URL = "https://sns.ap-southeast-1.amazonaws.com/SimpleNotificationService-abc.pem"


def sns_message(event: dict, version="2", topic="arn:aws:sns:ap-southeast-1:1:fw"):
    m = {"Type": "Notification", "MessageId": "m-1", "TopicArn": topic, "Message": json.dumps(event), "Timestamp": "2026-10-25T01:00:00.000Z", "SignatureVersion": version, "SigningCertURL": CERT_URL}
    h = hashes.SHA256() if version == "2" else hashes.SHA1()
    m["Signature"] = base64.b64encode(KEY.sign(webhooks._string_to_sign(m), padding.PKCS1v15(), h)).decode()
    return m


@pytest.fixture
def sns(monkeypatch):
    monkeypatch.setattr(webhooks, "fetch_cert", lambda url: PEM)


def post(client, m):
    return client.post("/api/webhooks/ses", content=json.dumps(m), headers={"content-type": "text/plain"})


def test_sns_signature_verified(client, sns):
    ev = {"notificationType": "Complaint", "complaint": {"complainedRecipients": [{"emailAddress": "angry@example.test"}]}}
    for v in ("1", "2"):
        assert post(client, sns_message(ev, v)).status_code == 200
    bad = sns_message(ev)
    bad["Message"] = bad["Message"].replace("angry", "other")
    assert post(client, bad).status_code == 403
    evil = sns_message(ev)
    evil["SigningCertURL"] = "https://evil.example.com/cert.pem"
    assert post(client, evil).status_code == 403
    assert post(client, {"Type": "Notification"}).status_code == 403


def test_bounce_complaint_delivery_feed_suppression_and_outbox(client, sns):
    with SessionLocal() as db:
        row = M.send_template(db, "welcome", "bouncer@example.test", "B", "en", {"building": "X"})
        row2 = M.send_template(db, "welcome", "happy@example.test", "H", "en", {"building": "X"})
        row2.delivered_at = None       # the sandbox provider stamps it at once; a real one waits for the SNS report
        db.commit()
        rid, rid2 = row.id, row2.id
        assert row.status == "sent"
    soft = {"notificationType": "Bounce", "bounce": {"bounceType": "Transient", "bounceSubType": "MailboxFull", "bouncedRecipients": [{"emailAddress": "bouncer@example.test"}]}}
    assert post(client, sns_message(soft)).json()["handled"] == 0
    hard = {"notificationType": "Bounce", "bounce": {"bounceType": "Permanent", "bounceSubType": "General", "bouncedRecipients": [{"emailAddress": "Bouncer@Example.test"}]}}
    assert post(client, sns_message(hard)).json()["handled"] == 1
    assert post(client, sns_message({"eventType": "Delivery", "delivery": {"recipients": ["happy@example.test"]}})).json()["handled"] == 1
    with SessionLocal() as db:
        assert db.get(MailOutbox, rid).status == "bounced"
        assert db.scalar(select(MailSuppression.reason).where(MailSuppression.email == "bouncer@example.test")) == "bounce"
        assert db.get(MailOutbox, rid2).delivered_at is not None
        again = M.send_template(db, "welcome", "bouncer@example.test", "B", "en", {"building": "X"})
        assert again.status == "suppressed"


def test_subscription_confirmation_only_to_amazon(client, sns, monkeypatch):
    got = []
    monkeypatch.setattr(webhooks.httpx, "get", lambda url, **kw: got.append(url) or type("R", (), {})())
    m = {"Type": "SubscriptionConfirmation", "MessageId": "1", "Token": "t", "TopicArn": "arn", "Message": "x", "SubscribeURL": "https://sns.ap-southeast-1.amazonaws.com/?Action=ConfirmSubscription&Token=t",
         "Timestamp": "2026-10-25T01:00:00.000Z", "SignatureVersion": "2", "SigningCertURL": CERT_URL}
    m["Signature"] = base64.b64encode(KEY.sign(webhooks._string_to_sign(m), padding.PKCS1v15(), hashes.SHA256())).decode()
    assert post(client, m).json()["confirmed"] and len(got) == 1
    m2 = dict(m, SubscribeURL="https://evil.test/confirm")
    m2["Signature"] = base64.b64encode(KEY.sign(webhooks._string_to_sign(m2), padding.PKCS1v15(), hashes.SHA256())).decode()
    post(client, m2)
    assert len(got) == 1


def test_topic_pinning(client, sns, monkeypatch):
    monkeypatch.setenv("SES_SNS_TOPIC_ARN", "arn:aws:sns:ap-southeast-1:1:right")
    ev = {"notificationType": "Delivery", "delivery": {"recipients": []}}
    assert post(client, sns_message(ev, topic="arn:aws:sns:ap-southeast-1:1:wrong")).status_code == 403
    assert post(client, sns_message(ev, topic="arn:aws:sns:ap-southeast-1:1:right")).status_code == 200
