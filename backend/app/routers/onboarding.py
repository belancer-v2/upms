"""Tenant onboarding, owner-led. The tenant fills a short form from an SMS link, a person checks it, and the DMP pack is printed and submitted by a person."""
import secrets
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Message
from ..models.core import Property, User, now
from ..models.onboarding import TenantCase, TenantDoc
from ..models.property import Occupancy, Unit
from ..permissions import COMMITTEE, MANAGE
from ..services import vault
from ..services.messaging import deliver

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
OWNERS = {"FLAT_OWNER", "OWNER_REP"}
REVIEW = MANAGE | {"SECRETARY"}
SEE_ALL = MANAGE | COMMITTEE | {"AUDITOR"}
REQUIRED_DOCS = ("nid_front", "nid_back", "photo")
DOC_KINDS = REQUIRED_DOCS + ("agreement", "noc", "employer")
REQUIRED_FIELDS = ("father_name", "permanent_address", "profession", "emergency_name", "emergency_phone", "reference_name", "reference_phone")
ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}


def _gate(ctx: Ctx):
    ctx.feature("tenant_dmp")


def _ev(c: TenantCase, key: str, by: str = "", note: str = "") -> None:
    c.events = [*c.events, {"at": now().isoformat(), "by": by, "key": key, "note": note}]


def _missing(db: Session, c: TenantCase) -> dict:
    docs = {d.kind: d for d in db.scalars(select(TenantDoc).where(TenantDoc.case_id == c.id).order_by(TenantDoc.id))}
    return {"fields": [f for f in REQUIRED_FIELDS if not str(c.details.get(f, "")).strip()] + (["nid"] if not c.nid_enc else []),
            "docs": [k for k in REQUIRED_DOCS if k not in docs], "docs_open": [k for k in REQUIRED_DOCS if k in docs and docs[k].status != "accepted"]}


def _doc(d: TenantDoc) -> dict:
    return {"id": d.id, "kind": d.kind, "filename": d.filename, "size": d.size, "content_type": d.content_type, "status": d.status, "note": d.note, "at": d.uploaded_at.isoformat()}


def _case(db: Session, c: TenantCase, units: dict, full: bool = False, staff_view: bool = True) -> dict:
    u = units.get(c.unit_id)
    d = {"id": c.id, "unit_id": c.unit_id, "unit": u.number if u else "", "status": c.status, "name": c.name, "phone": c.phone if staff_view else "", "rent": c.rent, "advance": c.advance,
         "start_date": c.start_date.isoformat(), "lease_months": c.lease_months, "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None, "police_ref": c.police_ref,
         "police_on": c.police_on.isoformat() if c.police_on else None, "receipt_no": c.receipt_no, "created_at": c.created_at.isoformat(), "missing": _missing(db, c), "nid": vault.mask(c.nid_last4)}
    if full:
        d["details"] = c.details
        d["docs"] = [_doc(x) for x in db.scalars(select(TenantDoc).where(TenantDoc.case_id == c.id).order_by(TenantDoc.id))]
        d["events"] = c.events
        d["token"] = c.token if staff_view else ""
    return d


def _units(db: Session, ctx: Ctx) -> dict:
    return {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}


def _mine(db: Session, ctx: Ctx, cid: int, units: dict) -> TenantCase:
    _gate(ctx)
    c = db.get(TenantCase, cid)
    if not c or c.property_id != ctx.property.id or (not ctx.has(*SEE_ALL) and c.unit_id not in ctx.unit_ids):
        raise HTTPException(404, "Not found")
    return c


@router.get("/cases")
def cases(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    units = _units(db, ctx)
    stmt = select(TenantCase).where(TenantCase.property_id == ctx.property.id).order_by(TenantCase.id.desc())
    if not ctx.has(*SEE_ALL):
        if not ctx.unit_ids or not ctx.has(*OWNERS):
            raise HTTPException(403, "Your role cannot do this")
        stmt = stmt.where(TenantCase.unit_id.in_(ctx.unit_ids))
    return [_case(db, c, units) for c in db.scalars(stmt)]


@router.get("/cases/{cid}")
def case(cid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    units = _units(db, ctx)
    return _case(db, _mine(db, ctx, cid, units), units, full=True)


class CaseIn(BaseModel):
    unit_id: int
    name: str = Field(min_length=2)
    phone: str = Field(min_length=6)
    rent: int = Field(ge=0)
    advance: int = Field(default=0, ge=0)
    start_date: date
    lease_months: int = Field(default=12, ge=1, le=120)


def _sms_link(db: Session, ctx: Ctx, c: TenantCase, key: str) -> None:
    body = f"{ctx.property.name_bn or ctx.property.name}: ভাড়াটিয়া তথ্য ফরম পূরণ করুন। লিংক: flatwise.app/t/{c.token}"
    if db.scalar(select(Message.id).where(Message.idem_key == key)):
        return
    m = Message(property_id=ctx.property.id, unit_id=c.unit_id, to_name=c.name, to_phone=c.phone, template="tenant_form", lang="bn", body=body, idem_key=key)
    db.add(m)
    deliver(db, ctx.property.org_id, m)


@router.post("/cases", status_code=201)
def create(body: CaseIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    units = _units(db, ctx)
    u = units.get(body.unit_id)
    if not u:
        raise HTTPException(404, "Flat not found")
    owner_led = ctx.has(*OWNERS) and u.id in ctx.unit_ids
    if not owner_led:
        ctx.need(*REVIEW)
        if u.status != "to_let":
            raise HTTPException(422, "The owner must approve letting this flat first")
    if db.scalar(select(Occupancy.id).where(Occupancy.unit_id == u.id, Occupancy.kind == "tenant", Occupancy.active)):
        raise HTTPException(422, "This flat already has a tenant. Move them out first.")
    if db.scalar(select(TenantCase.id).where(TenantCase.unit_id == u.id, TenantCase.status.in_(("invited", "review", "verified", "police")))):
        raise HTTPException(409, "There is already an onboarding case open for this flat")
    c = TenantCase(property_id=ctx.property.id, unit_id=u.id, token=secrets.token_urlsafe(14), name=body.name, phone=body.phone, rent=body.rent, advance=body.advance, start_date=body.start_date,
                   lease_months=body.lease_months, created_by=ctx.user.id)
    db.add(c)
    db.flush()
    _ev(c, "invited", ctx.user.name)
    _sms_link(db, ctx, c, f"tcase{c.id}:invite")
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="onboarding.create", entity="case", entity_id=c.id, meta={"unit": u.number})
    db.commit()
    return _case(db, c, units, full=True)


@router.post("/cases/{cid}/resend")
def resend(cid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    if c.status != "invited":
        raise HTTPException(422, "The tenant has already sent the form")
    _sms_link(db, ctx, c, f"tcase{c.id}:resend:{date.today().isoformat()}")
    db.commit()
    return {"ok": True}


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")
    note: str = ""


@router.post("/cases/{cid}/docs/{did}/review")
def review_doc(cid: int, did: int, body: ReviewIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    ctx.need(*REVIEW)
    d = db.get(TenantDoc, did)
    if not d or d.case_id != c.id:
        raise HTTPException(404, "Not found")
    d.status, d.note = body.status, body.note[:160]
    if body.status == "rejected" and c.status in ("review",):
        c.status = "invited"          # back to the tenant, who fixes just that document
        _ev(c, "doc_rejected", ctx.user.name, f"{d.kind}: {body.note}")
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"onboarding.doc.{body.status}", entity="case", entity_id=c.id, meta={"kind": d.kind})
    db.commit()
    return _case(db, c, units, full=True)


@router.get("/cases/{cid}/docs/{did}/file")
def doc_file(cid: int, did: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    ctx.need(*(REVIEW | {"PRESIDENT"}))
    d = db.get(TenantDoc, did)
    path = config.UPLOAD_DIR / str(c.id) / (d.stored if d else "x")
    if not d or d.case_id != c.id or not path.exists():
        raise HTTPException(404, "Not found")
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="onboarding.doc.view", entity="case", entity_id=c.id, meta={"kind": d.kind})
    db.commit()
    return FileResponse(path, media_type=d.content_type, filename=d.filename)


@router.post("/cases/{cid}/verify")
def verify(cid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """A person confirms the form and documents are complete. The tenant is added to the flat."""
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    ctx.need(*REVIEW)
    if c.status != "review":
        raise HTTPException(422, "The tenant has not sent the form yet")
    m = _missing(db, c)
    if m["fields"] or m["docs"] or m["docs_open"]:
        raise HTTPException(422, "Some details or documents are missing or not accepted yet")
    u = units[c.unit_id]
    if db.scalar(select(Occupancy.id).where(Occupancy.unit_id == u.id, Occupancy.kind == "tenant", Occupancy.active)):
        raise HTTPException(422, "This flat already has a tenant. Move them out first.")
    occ = Occupancy(unit_id=u.id, kind="tenant", name=c.name, phone=c.phone, start_date=c.start_date)
    db.add(occ)
    u.status = "occupied"
    db.flush()
    c.occupancy_id, c.status = occ.id, "verified"
    _ev(c, "verified", ctx.user.name)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="onboarding.verify", entity="case", entity_id=c.id)
    db.commit()
    return _case(db, c, units, full=True)


class PoliceIn(BaseModel):
    reference_no: str = Field(min_length=2, max_length=60)
    submitted_on: date


@router.post("/cases/{cid}/police")
def police(cid: int, body: PoliceIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Recorded by a person after they hand in the printed pack. The system never files anything itself."""
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    ctx.need(*REVIEW)
    if c.status != "verified":
        raise HTTPException(422, "Verify the case first")
    c.status, c.police_ref, c.police_on = "police", body.reference_no, body.submitted_on
    _ev(c, "police", ctx.user.name, body.reference_no)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="onboarding.police", entity="case", entity_id=c.id, meta={"ref": body.reference_no})
    db.commit()
    return _case(db, c, units, full=True)


class AckIn(BaseModel):
    receipt_no: str = Field(min_length=2, max_length=60)


@router.post("/cases/{cid}/done")
def done(cid: int, body: AckIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    ctx.need(*REVIEW)
    if c.status != "police":
        raise HTTPException(422, "Record the police submission first")
    c.status, c.receipt_no = "done", body.receipt_no
    _ev(c, "done", ctx.user.name, body.receipt_no)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="onboarding.done", entity="case", entity_id=c.id)
    db.commit()
    return _case(db, c, units, full=True)


@router.post("/cases/{cid}/cancel")
def cancel(cid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    if c.status not in ("invited", "review") or not (ctx.has(*REVIEW) or c.created_by == ctx.user.id):
        raise HTTPException(403, "Your role cannot do this")
    c.status = "cancelled"
    _ev(c, "cancelled", ctx.user.name)
    db.commit()
    return _case(db, c, units, full=True)


@router.get("/cases/{cid}/pack")
def pack(cid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Everything the DMP tenant form asks for, in one place, ready to print. Full ID is shown here and the view is logged."""
    units = _units(db, ctx)
    c = _mine(db, ctx, cid, units)
    ctx.need(*(REVIEW | {"PRESIDENT"}))
    if c.status not in ("verified", "police", "done"):
        raise HTTPException(422, "Verify the case before printing the pack")
    u = units[c.unit_id]
    owners = db.scalars(select(Occupancy).where(Occupancy.unit_id == u.id, Occupancy.kind == "owner", Occupancy.active)).all()
    p = ctx.property
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=p.id, action="onboarding.pack.view", entity="case", entity_id=c.id)
    db.commit()
    return {"building": p.name, "building_bn": p.name_bn, "address": p.address, "unit": u.number, "floor": u.floor, "block": u.block, "area_sqft": u.area_sqft, "bedrooms": u.bedrooms,
            "owners": [{"name": o.name, "name_bn": o.name_bn, "phone": o.phone} for o in owners], "tenant": {"name": c.name, "phone": c.phone, "nid": vault.unseal(c.nid_enc)},
            "details": c.details, "rent": c.rent, "advance": c.advance, "start_date": c.start_date.isoformat(), "lease_months": c.lease_months,
            "docs": [{"kind": d.kind, "status": d.status} for d in db.scalars(select(TenantDoc).where(TenantDoc.case_id == c.id))], "status": c.status, "police_ref": c.police_ref,
            "police_on": c.police_on.isoformat() if c.police_on else None, "printed_on": date.today().isoformat()}


# ---------------- the tenant's own link: no sign-in
def _by_token(db: Session, token: str) -> TenantCase:
    c = db.scalar(select(TenantCase).where(TenantCase.token == token))
    if not c or c.status == "cancelled":
        raise HTTPException(404, "This link is not valid")
    return c


@router.get("/link/{token}")
def link_get(token: str, db: Session = Depends(get_db)):
    c = _by_token(db, token)
    p, u = db.get(Property, c.property_id), db.get(Unit, c.unit_id)
    return {"building": p.name, "building_bn": p.name_bn, "address": p.address, "unit": u.number, "name": c.name, "rent": c.rent, "advance": c.advance, "start_date": c.start_date.isoformat(),
            "status": c.status, "details": c.details, "nid": vault.mask(c.nid_last4), "locked": c.status not in ("invited",),
            "docs": [_doc(d) for d in db.scalars(select(TenantDoc).where(TenantDoc.case_id == c.id).order_by(TenantDoc.id))], "missing": _missing(db, c)}


class DetailsIn(BaseModel):
    father_name: str = ""
    mother_name: str = ""
    permanent_address: str = ""
    previous_address: str = ""
    profession: str = ""
    employer: str = ""
    nid: str = ""
    family: list[dict] = []
    emergency_name: str = ""
    emergency_phone: str = ""
    reference_name: str = ""
    reference_phone: str = ""


@router.put("/link/{token}")
def link_save(token: str, body: DetailsIn, db: Session = Depends(get_db)):
    c = _by_token(db, token)
    if c.status != "invited":
        raise HTTPException(423, "The form has been sent. It can not be changed now.")
    nid = "".join(ch for ch in body.nid if ch.isdigit())
    if body.nid and len(nid) not in (10, 13, 17):
        raise HTTPException(422, "A National ID has 10, 13 or 17 digits")
    data = body.model_dump(exclude={"nid"})
    data["family"] = [{"name": str(f.get("name", ""))[:80], "relation": str(f.get("relation", ""))[:30], "age": str(f.get("age", ""))[:3]} for f in body.family[:12] if str(f.get("name", "")).strip()]
    c.details = {**c.details, **{k: v for k, v in data.items() if v not in ("", None) or k == "family"}}
    if nid:
        c.nid_enc, c.nid_last4 = vault.seal(nid), nid[-4:]
    db.commit()
    return link_get(token, db)


@router.post("/link/{token}/docs", status_code=201)
async def link_upload(token: str, kind: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    c = _by_token(db, token)
    if c.status != "invited":
        raise HTTPException(423, "The form has been sent. It can not be changed now.")
    if kind not in DOC_KINDS:
        raise HTTPException(422, "Unknown document type")
    ext = ALLOWED.get(file.content_type or "")
    if not ext:
        raise HTTPException(422, "Upload a photo (JPG or PNG) or a PDF")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is bigger than 3 MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    folder = config.UPLOAD_DIR / str(c.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(10)}.{ext}"
    (folder / stored).write_bytes(data)
    for old in db.scalars(select(TenantDoc).where(TenantDoc.case_id == c.id, TenantDoc.kind == kind)):
        db.delete(old)       # a new upload replaces the earlier one for that slot
    db.add(TenantDoc(case_id=c.id, kind=kind, filename=(file.filename or stored)[:160], stored=stored, content_type=file.content_type, size=len(data)))
    db.commit()
    return link_get(token, db)


@router.post("/link/{token}/submit")
def link_submit(token: str, db: Session = Depends(get_db)):
    c = _by_token(db, token)
    if c.status != "invited":
        raise HTTPException(423, "Already sent")
    m = _missing(db, c)
    if m["fields"] or m["docs"]:
        raise HTTPException(422, "Please fill the missing details and upload the required documents")
    for d in db.scalars(select(TenantDoc).where(TenantDoc.case_id == c.id, TenantDoc.status == "rejected")):
        d.status, d.note = "pending", ""
    c.status, c.submitted_at = "review", now()
    _ev(c, "submitted", c.name)
    db.commit()
    return link_get(token, db)
