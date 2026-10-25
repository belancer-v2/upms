"""Real email sending for services/mailer.py: SMTP (STARTTLS or SSL) and Amazon SES through its SMTP interface.

Env: MAIL_SMTP_HOST, MAIL_SMTP_PORT (587), MAIL_SMTP_USER, MAIL_SMTP_PASSWORD, MAIL_SMTP_SECURITY=starttls|ssl|none (starttls),
MAIL_FROM ("FlatWise <hello@example.com>"), MAIL_REPLY_TO, MAIL_SMTP_TIMEOUT (15), MAIL_SMTP_RETRIES (2).
SES: MAIL_PROVIDER=ses with SES_REGION (host becomes email-smtp.<region>.amazonaws.com) and the SES *SMTP* credentials in MAIL_SMTP_USER / MAIL_SMTP_PASSWORD;
SES_CONFIGURATION_SET adds the X-SES-CONFIGURATION-SET header so bounce/complaint events reach the SNS topic.
Passwords are never logged. Verified only against a fake SMTP server in tests.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

log = logging.getLogger("flatwise.mail")


class MailError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def build_message(to: str, subject: str, html: str, text: str, headers: dict | None = None) -> EmailMessage:
    sender = os.getenv("MAIL_FROM", "")
    if not parseaddr(sender)[1]:
        raise MailError("MAIL_FROM is not set")
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, to, subject
    m["Date"], m["Message-ID"] = formatdate(localtime=False), make_msgid(domain=parseaddr(sender)[1].split("@")[-1])
    if os.getenv("MAIL_REPLY_TO"):
        m["Reply-To"] = os.environ["MAIL_REPLY_TO"]
    for k, v in (headers or {}).items():
        m[k] = v
    m.set_content(text or " ")
    m.add_alternative(html, subtype="html")
    return m


def smtp_send(msg: EmailMessage, host: str, port: int, user: str, password: str, security: str = "starttls", timeout: float = 15.0, retries: int = 2,
              factory=None, sleep=time.sleep) -> str:
    """Sends one message. Retries connection problems and 4xx (temporary) replies with backoff; 5xx replies are permanent. Returns the Message-ID."""
    last = ""
    for attempt in range(retries + 1):
        try:
            if factory:
                s = factory(host, port, timeout)
            elif security == "ssl":
                s = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
            else:
                s = smtplib.SMTP(host, port, timeout=timeout)
            with s:
                if security == "starttls":
                    s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, password)
                s.send_message(msg)
            return str(msg["Message-ID"])
        except smtplib.SMTPRecipientsRefused as e:
            raise MailError("Recipient refused: " + "; ".join(str(v[0]) for v in e.recipients.values())[:80])
        except smtplib.SMTPAuthenticationError:
            raise MailError("SMTP login failed (check MAIL_SMTP_USER / MAIL_SMTP_PASSWORD)")
        except smtplib.SMTPResponseException as e:
            if 500 <= e.smtp_code < 600:
                raise MailError(f"SMTP {e.smtp_code}: {str(e.smtp_error)[:60]}")
            last = f"SMTP {e.smtp_code}"
        except (smtplib.SMTPException, OSError) as e:
            last = type(e).__name__
        if attempt < retries:
            sleep(0.5 * (2 ** attempt))
    log.warning("smtp send failed after %d tries: %s", retries + 1, last)
    raise MailError(f"Mail server unreachable ({last})", retryable=True)


def settings(kind: str) -> dict:
    e = os.getenv
    if kind == "ses":
        region = e("SES_REGION", "")
        host = e("MAIL_SMTP_HOST") or (f"email-smtp.{region}.amazonaws.com" if region else "")
    else:
        host = e("MAIL_SMTP_HOST", "")
    if not host:
        raise MailError("MAIL_SMTP_HOST (or SES_REGION for SES) is not set")
    return {"host": host, "port": int(e("MAIL_SMTP_PORT", "587")), "user": e("MAIL_SMTP_USER", ""), "password": e("MAIL_SMTP_PASSWORD", ""),
            "security": e("MAIL_SMTP_SECURITY", "starttls").lower(), "timeout": float(e("MAIL_SMTP_TIMEOUT", "15")), "retries": int(e("MAIL_SMTP_RETRIES", "2"))}
