"""Optional online payment of service-charge invoices. Sandbox provider only; see services/gateway.py."""
import json
import logging
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..services.ratelimit import limit as rate_limit
from ..db import get_db
from ..deps import Ctx, current_user, property_ctx
from ..models.billing import Invoice, Payment
from ..models.core import Property, User, now
from ..models.gateway import GatewayConfig, GatewaySession
from ..models.property import Unit
from ..permissions import MANAGE
from ..services import gateway as gw
from ..services import vault
from ..services.http_util import ProviderError
from ..services.entitlements import org_features
from . import billing as B

router = APIRouter(prefix="/api/gateway", tags=["gateway"])
ADMIN = MANAGE | {"TREASURER"}


def _gate(ctx: Ctx) -> None:
    ctx.feature("gateway")


def _cfg(db: Session, property_id: int) -> GatewayConfig | None:
    return db.scalar(select(GatewayConfig).where(GatewayConfig.property_id == property_id))


def _cfg_out(c: GatewayConfig | None) -> dict:
    # credentials are never returned, only whether some are stored
    if not c:
        return {"enabled": False, "providers": [], "fee_mode": "building_absorbs", "fee_bps": 0, "has_credentials": False}
    return {"enabled": c.enabled, "providers": list(c.providers or []), "fee_mode": c.fee_mode, "fee_bps": c.fee_bps, "has_credentials": bool(c.credentials_enc)}


def _aware(d):
    return d if d.tzinfo else d.replace(tzinfo=now().tzinfo)


def _out(s: GatewaySession, unit: str = "", inv: Invoice | None = None) -> dict:
    return {"id": s.id, "token": s.token, "invoice_id": s.invoice_id, "invoice": inv.number if inv else "", "period": inv.period if inv else "", "unit": unit, "provider": s.provider,
            "amount": s.amount, "fee": s.fee, "fee_mode": s.fee_mode, "charged": s.charged, "status": s.status, "provider_ref": s.provider_ref, "trx_id": s.trx_id,
            "payment_id": s.payment_id, "created_at": s.created_at.isoformat(), "completed_at": s.completed_at.isoformat() if s.completed_at else None}


@router.get("/options")
def options(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """What a resident may pick on the pay screen. Never an error: a building without the feature just reports it off."""
    c = _cfg(db, ctx.property.id)
    if "gateway" not in ctx.features or not c or not c.enabled or not c.providers:
        return {"enabled": False, "providers": [], "fee_mode": "building_absorbs", "fee_bps": 0}
    return {"enabled": True, "providers": list(c.providers), "fee_mode": c.fee_mode, "fee_bps": c.fee_bps}


@router.get("/config")
def get_config(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ADMIN)
    return _cfg_out(_cfg(db, ctx.property.id))


class ConfigIn(BaseModel):
    enabled: bool
    providers: list[str] = []
    fee_mode: str = Field(default="building_absorbs", pattern="^(building_absorbs|payer_pays)$")
    fee_bps: int = Field(default=0, ge=0, le=gw.MAX_FEE_BPS)
    credentials: dict | None = None   # write-only; sealed with the vault key. Omit to keep what is stored.


@router.put("/config")
def put_config(body: ConfigIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ADMIN)
    provs = [p for p in gw.PROVIDERS if p in body.providers]
    if len(provs) != len(set(body.providers)):
        raise HTTPException(422, "Unknown provider")
    if body.enabled and not provs:
        raise HTTPException(422, "Pick at least one provider")
    c = _cfg(db, ctx.property.id)
    if not c:
        c = GatewayConfig(property_id=ctx.property.id)
        db.add(c)
    c.enabled, c.providers, c.fee_mode, c.fee_bps = body.enabled, provs, body.fee_mode, body.fee_bps
    if body.credentials is not None:
        c.credentials_enc = vault.seal(json.dumps(body.credentials)) if body.credentials else ""
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="gateway.config", entity="gateway", entity_id=ctx.property.id,
          meta={"enabled": c.enabled, "providers": provs, "fee_mode": c.fee_mode, "fee_bps": c.fee_bps, "credentials_changed": body.credentials is not None})
    db.commit()
    return _cfg_out(c)


class CheckoutIn(BaseModel):
    invoice_id: int
    provider: str
    amount: int | None = Field(default=None, gt=0)   # paisa; omit to pay the whole balance


@router.post("/checkout", status_code=201)
def checkout(body: CheckoutIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    inv = db.get(Invoice, body.invoice_id)
    if not inv or inv.property_id != ctx.property.id or inv.status == "void":
        raise HTTPException(404, "Not found")
    if inv.unit_id not in ctx.unit_ids:
        raise HTTPException(403, "Only the people of this flat can pay it online")
    c = _cfg(db, ctx.property.id)
    if not c or not c.enabled or body.provider not in (c.providers or []):
        raise HTTPException(422, "Online payment is not available for this method")
    balance = inv.total - inv.paid
    amount = body.amount if body.amount is not None else balance
    if balance <= 0 or amount <= 0 or amount > balance:
        raise HTTPException(422, "Amount must be more than zero and not more than the balance")
    fee = gw.fee_for(amount, c.fee_bps)
    charged = amount + fee if c.fee_mode == "payer_pays" else amount
    token = secrets.token_urlsafe(24)
    try:
        co = gw.provider(body.provider).create_checkout(inv, charged, token=token, user=ctx.user)
    except ProviderError as e:      # the provider refused or is down: nothing was created, say so plainly
        raise HTTPException(502, "The payment provider is not available right now. Please try again in a few minutes.") from e
    s = GatewaySession(token=co["session_id"], property_id=ctx.property.id, invoice_id=inv.id, unit_id=inv.unit_id, user_id=ctx.user.id, provider=body.provider, amount=amount, fee=fee,
                       fee_mode=c.fee_mode, charged=charged, provider_ref=co["provider_ref"], idem_key=f"gw:{co['session_id']}",
                       expires_at=now() + timedelta(minutes=gw.SESSION_MINUTES))
    db.add(s)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="gateway.checkout", entity="invoice", entity_id=inv.id, meta={"provider": body.provider, "amount": amount, "fee": fee})
    db.commit()
    return {"session_id": s.token, "redirect_url": co["redirect_url"], "amount": s.amount, "fee": s.fee, "charged": s.charged}


def _mine(db: Session, token: str, user: User) -> GatewaySession:
    s = db.scalar(select(GatewaySession).where(GatewaySession.token == token))
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Not found")
    return s


@router.get("/sandbox/{token}")
def sandbox(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The sandbox 'provider' hosted page asks for its details. It hands back the payloads a real provider would post to the callback."""
    from .. import config as _cfg
    if not _cfg.SANDBOX_PAYMENTS:      # the practice provider hands the payer a signed "success": it must not exist in production
        raise HTTPException(404, "Not found")
    s = _mine(db, token, user)
    inv = db.get(Invoice, s.invoice_id)
    pr = gw.provider(s.provider)
    trx = pr.sandbox_trx(s.token)
    payload = lambda st: {"session": s.token, "status": st, "trx_id": trx if st == "success" else "", "amount": s.charged, "sig": gw.sign(s.token, st, s.charged, trx if st == "success" else "")}  # noqa: E731
    prop = db.get(Property, s.property_id)
    return {**_out(s, inv=inv), "building": prop.name if prop else "", "building_bn": prop.name_bn if prop else "", "pay": payload("success"), "fail": payload("failed")}


class CallbackIn(BaseModel):
    status: str
    trx_id: str = ""
    amount: int
    sig: str


@router.post("/callback/{token}", dependencies=[Depends(rate_limit("callback", 60, 60))])
def callback(token: str, body: CallbackIn, db: Session = Depends(get_db)):
    """Called by the provider (in the sandbox: by the hosted page). No sign-in; the signed payload is the proof."""
    s = db.scalar(select(GatewaySession).where(GatewaySession.token == token))
    if not s:
        raise HTTPException(404, "Not found")
    res = gw.provider(s.provider, sandbox=True).verify({"session": token, **body.model_dump()})
    if not res["valid"]:
        raise HTTPException(403, "Bad signature")
    if s.status == "paid":                                  # replayed callback: same answer, no second payment
        return {"status": "paid", "payment_id": s.payment_id, "invoice_id": s.invoice_id, "replayed": True}
    if s.status in ("failed", "expired"):
        raise HTTPException(409, f"This payment session is {s.status}")
    prop = db.get(Property, s.property_id)
    if "gateway" not in org_features(db, prop.org_id):
        raise HTTPException(402, "Your plan does not include 'gateway'")
    if _aware(s.expires_at) < now():
        s.status, s.completed_at = "expired", now()
        db.commit()
        raise HTTPException(410, "This payment session expired")
    if not res["ok"]:
        s.status, s.completed_at = "failed", now()
        audit(db, user_id=s.user_id, org_id=prop.org_id, property_id=prop.id, action="gateway.failed", entity="gateway_session", entity_id=s.id)
        db.commit()
        return {"status": "failed", "payment_id": None, "invoice_id": s.invoice_id}
    return settle_paid(db, s, res["trx_id"], res["amount"])


def settle_paid(db: Session, s: GatewaySession, trx_id: str, amount: int, *, confirmed: bool = False, source: str = "callback") -> dict:
    """Turns a paid session into ONE verified payment. Idempotent: a session that is already paid answers the same way.
    confirmed=True means the provider itself told us (server to server) that the money was taken, so a session our clock called
    expired or failed is still honoured; only an invoice that can no longer accept the amount refuses. Raises HTTPException."""
    if s.status == "paid":
        return {"status": "paid", "payment_id": s.payment_id, "invoice_id": s.invoice_id, "replayed": True}
    if not confirmed and s.status in ("failed", "expired"):
        raise HTTPException(409, f"This payment session is {s.status}")
    prop = db.get(Property, s.property_id)
    inv = db.get(Invoice, s.invoice_id)
    # server-side amount checks: what the provider says it took, and what the invoice can still accept
    if amount != s.charged:
        raise HTTPException(422, "Amount does not match the checkout")
    if inv.status == "void" or s.amount > inv.total - inv.paid:
        s.status, s.completed_at = "failed", now()
        db.commit()
        raise HTTPException(409, "The invoice no longer accepts this amount")
    if db.scalar(select(Payment.id).where(Payment.property_id == s.property_id, Payment.trx_id == trx_id[:40], Payment.status != "rejected")) and trx_id:
        raise HTTPException(409, "This transaction was already recorded")
    user = db.get(User, s.user_id)
    p = Payment(property_id=s.property_id, invoice_id=inv.id, unit_id=inv.unit_id, amount=s.amount, method=s.provider, trx_id=trx_id[:40], paid_on=now().date(), status="pending",
                submitted_by=s.user_id, note=f"Online payment {s.provider_ref}"[:200])
    db.add(p)
    db.flush()
    # same path as billing: verified, receipt number, invoice refresh, then the ledger hook
    B._verify(db, Ctx(user=user, property=prop, roles=set(), features=org_features(db, prop.org_id)), p)
    p.verified_by = None                                    # confirmed by the gateway, not by a person
    s.status, s.trx_id, s.payment_id, s.completed_at = "paid", p.trx_id, p.id, now()
    audit(db, user_id=s.user_id, org_id=prop.org_id, property_id=prop.id, action="gateway.paid", entity="payment", entity_id=p.id, meta={"session": s.id, "amount": s.amount, "fee": s.fee, "provider": s.provider, "source": source})
    db.commit()
    return {"status": "paid", "payment_id": p.id, "invoice_id": inv.id, "receipt_no": p.receipt_no}


log = logging.getLogger("flatwise.gateway")


def _back(outcome: str, token: str) -> RedirectResponse:
    origin = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    return RedirectResponse(f"{origin}/pay/return/{outcome}?session={token}", status_code=303)


def _finish(db: Session, s: GatewaySession, res: dict, source: str) -> str:
    """Applies a provider-confirmed result to the session. Returns success | fail | cancel | error."""
    if res["status"] == "paid":
        try:
            settle_paid(db, s, res["trx_id"], res["amount"], confirmed=True, source=source)
            return "success"
        except HTTPException as e:
            db.rollback()
            log.warning("session %s paid at provider but not settled: %s", s.id, e.detail)
            return "error"
    if res["status"] in ("failed", "cancelled") and s.status == "created":
        s.status, s.completed_at = "failed", now()
        db.commit()
    return "cancel" if res["status"] == "cancelled" else "fail" if res["status"] in ("failed",) else "error"


@router.api_route("/return/{token}", methods=["GET", "POST"], operation_id="gateway_provider_return", dependencies=[Depends(rate_limit("pret", 60, 60))])
async def provider_return(token: str, request: Request, db: Session = Depends(get_db)):
    """Where the customer's browser lands after a real provider (bKash GET, SSLCommerz POST). The redirect is NOT trusted:
    the adapter asks the provider server to server what happened, and only that answer can mark the invoice paid."""
    s = db.scalar(select(GatewaySession).where(GatewaySession.token == token))
    if not s:
        raise HTTPException(404, "Not found")
    prov = gw.provider(s.provider)
    if not prov.live:
        raise HTTPException(404, "Not found")
    params = dict(request.query_params)
    if request.method == "POST":
        params.update({k: str(v) for k, v in (await request.form()).items()})
    if s.status == "paid":
        return _back("success", token)
    try:
        res = prov.finalize(s, params)
    except ProviderError as e:
        log.warning("finalize failed for session %s: %s", s.id, e)
        return _back("error", token)
    return _back(_finish(db, s, res, "return"), token)


@router.post("/ipn/sslcommerz", dependencies=[Depends(rate_limit("ipn", 120, 60))])
async def ipn_sslcommerz(request: Request, db: Session = Depends(get_db)):
    """SSLCommerz server-to-server notification. Needs a valid verify_sign hash AND a successful validation API call."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    prov = gw.provider("card")
    if not prov.live or not hasattr(prov, "ipn"):
        raise HTTPException(404, "Not found")
    s = db.scalar(select(GatewaySession).where(GatewaySession.token == form.get("tran_id", "")))
    if not s:
        raise HTTPException(404, "Not found")
    try:
        res = prov.ipn(form)
    except ProviderError:
        raise HTTPException(502, "Validation unavailable, will be retried")
    if res is None:
        raise HTTPException(403, "Bad signature")
    if res["status"] == "paid" and res.get("tran_id") not in ("", s.token):
        raise HTTPException(403, "Transaction mismatch")
    out = _finish(db, s, res, "ipn")
    return {"ok": out in ("success", "fail", "cancel")}


@router.get("/sessions")
def sessions(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), q: str = "", status: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ADMIN)
    stmt = select(GatewaySession, Unit, Invoice).join(Unit, Unit.id == GatewaySession.unit_id).join(Invoice, Invoice.id == GatewaySession.invoice_id).where(GatewaySession.property_id == ctx.property.id)
    if status:
        stmt = stmt.where(GatewaySession.status == status)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Unit.number.ilike(like), Invoice.number.ilike(like), GatewaySession.trx_id.ilike(like), GatewaySession.provider_ref.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(GatewaySession.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "rows": [_out(s, u.number, i) for s, u, i in rows]}
