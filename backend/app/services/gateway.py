"""Payment gateway providers. SandboxProvider (default, no network) plus real bKash and SSLCommerz adapters in gateway_bkash.py / gateway_sslcommerz.py,
switched on by BKASH_MODE / SSLCOMMERZ_MODE. The real adapters are verified against mocks only: see docs/PAYMENTS_SETUP.md.

Original note: the sandbox needs no credentials, no network.

A real provider (bKash tokenized checkout, Nagad, SSLCommerz) replaces `SandboxProvider` behind the same two calls:
  create_checkout(invoice, amount) -> {session_id, redirect_url}
  verify(payload)                  -> {ok, trx_id, amount}
Callbacks are authenticated by an HMAC over (session, status, amount, trx_id) with SECRET_KEY.
"""
import hashlib
import hmac
import os
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models.billing import Invoice

PROVIDERS = ("bkash", "nagad", "card")
FEE_MODES = ("building_absorbs", "payer_pays")
MAX_FEE_BPS = 1000
SESSION_MINUTES = 30


def fee_for(amount: int, bps: int) -> int:
    """Gateway fee in whole paisa, rounded half up. Integer maths only."""
    return (amount * bps + 5000) // 10000


def sign(session: str, status: str, amount: int, trx_id: str) -> str:
    msg = f"gw|{session}|{status}|{amount}|{trx_id}".encode()
    return hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


class SandboxProvider:
    live = False

    def __init__(self, key: str):
        self.key = key

    def create_checkout(self, invoice: Invoice, amount: int, *, token: str = "", user=None) -> dict:
        sid = token or secrets.token_urlsafe(24)
        return {"session_id": sid, "redirect_url": f"/pay/sandbox/{sid}", "provider_ref": f"{self.key.upper()}-SBX-{sid[:8]}"}

    def verify(self, payload: dict) -> dict:
        """Checks the signature on a callback payload. ok is True only for a genuine success."""
        sid, status, trx, amt, sig = str(payload.get("session", "")), str(payload.get("status", "")), str(payload.get("trx_id", "")), payload.get("amount"), str(payload.get("sig", ""))
        if not config.SANDBOX_PAYMENTS or not isinstance(amt, int) or isinstance(amt, bool) or not hmac.compare_digest(sig.encode(), sign(sid, status, amt, trx).encode()):
            return {"ok": False, "valid": False, "trx_id": trx, "amount": 0}
        return {"ok": status == "success", "valid": True, "trx_id": trx, "amount": amt}

    def sandbox_trx(self, session: str) -> str:
        return "SBX" + hashlib.sha256(f"{self.key}|{session}".encode()).hexdigest()[:10].upper()


TRANSPORT = None   # tests set an httpx.MockTransport here; production leaves it None


def _mode(var: str) -> str:
    return os.getenv(var, "off").strip().lower()


def provider(key: str, sandbox: bool = False):
    """The adapter for a payment method. BKASH_MODE / SSLCOMMERZ_MODE = sandbox|live switch on the real adapters (off = built-in simulator).
    sandbox=True always returns the simulator (used by SMS/email credit purchases, which have no real checkout yet)."""
    if key not in PROVIDERS:
        raise ValueError("Unknown provider")
    if not sandbox:
        if key == "bkash" and _mode("BKASH_MODE") in ("sandbox", "live"):
            from .gateway_bkash import BkashProvider
            return BkashProvider(transport=TRANSPORT)
        if key in [k.strip() for k in os.getenv("SSLCOMMERZ_KEYS", "card").split(",")] and _mode("SSLCOMMERZ_MODE") in ("sandbox", "live"):
            from .gateway_sslcommerz import SslCommerzProvider
            return SslCommerzProvider(key, transport=TRANSPORT)
    return SandboxProvider(key)


def seed_gateway(db, ctx) -> None:
    """Demo: Sunrise takes online payments, with a few paid sessions tied to existing verified payments."""
    from datetime import timedelta

    from ..models.billing import Payment
    from ..models.core import now
    from ..models.gateway import GatewayConfig, GatewaySession
    from . import vault
    prop = ctx["sunrise"]
    db.add(GatewayConfig(property_id=prop.id, enabled=True, providers=["bkash", "nagad", "card"], fee_mode="payer_pays", fee_bps=150, credentials_enc=vault.seal("sandbox")))
    pays = db.scalars(select(Payment).where(Payment.property_id == prop.id, Payment.status == "verified", Payment.method.in_(("bkash", "nagad"))).order_by(Payment.id.desc()).limit(3)).all()
    for n, p in enumerate(pays):
        fee = fee_for(p.amount, 150)
        tok = f"seed-{prop.id}-{p.id}"
        db.add(GatewaySession(token=tok, property_id=prop.id, invoice_id=p.invoice_id, unit_id=p.unit_id, user_id=p.submitted_by or 0, provider=p.method, amount=p.amount, fee=fee, fee_mode="payer_pays",
                              charged=p.amount + fee, status="paid", provider_ref=f"{p.method.upper()}-SBX-{n}", trx_id=p.trx_id or f"SBXSEED{n}", payment_id=p.id, idem_key=f"gw:{tok}",
                              expires_at=now() + timedelta(minutes=SESSION_MINUTES), completed_at=now()))
    if pays:
        f = fee_for(100000, 150)
        db.add(GatewaySession(token=f"seed-{prop.id}-failed", property_id=prop.id, invoice_id=pays[0].invoice_id, unit_id=pays[0].unit_id, user_id=0, provider="card", amount=100000, fee=f,
                              fee_mode="payer_pays", charged=100000 + f, status="failed", provider_ref="CARD-SBX-seed", idem_key=f"gw:seed-{prop.id}-failed",
                              expires_at=now() + timedelta(minutes=SESSION_MINUTES), completed_at=now()))
    db.flush()
