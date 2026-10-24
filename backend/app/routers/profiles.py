"""Profiles: optional photo and details for users, occupants (owners/tenants) and staff.

Privacy: everyone with access to the building sees name and photo. Personal details (about, birthday, blood group,
profession, emergency contact, address, languages) are shown only to the person themself, to whoever may edit them,
and to roles that already see contacts (permissions.SEE_CONTACTS).
"""
import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..deps import Ctx, current_user, property_ctx
from ..models.core import Membership, User, now
from ..models.profile import Profile
from ..models.property import Occupancy, Unit
from ..models.staff import Staff
from ..permissions import MANAGE, SEE_CONTACTS

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
KINDS = ("user", "occupant", "staff")
MAX_PHOTO = 2 * 1024 * 1024
TYPES = {"image/jpeg": "jpg", "image/png": "png"}
BLOOD = {"", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
EDIT_OCC = MANAGE | {"SECRETARY"}
OWNERS = {"FLAT_OWNER", "OWNER_REP"}


def avatar_dir() -> Path:
    d = config.UPLOAD_DIR / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


class Access:
    def __init__(self, name: str, name_bn: str, see: bool, edit: bool, ctx: Ctx | None):
        self.name, self.name_bn, self.see, self.edit, self.ctx = name, name_bn, see, edit, ctx


def _ctx_for(db: Session, user: User, xpid: int) -> Ctx:
    return property_ctx(x_property_id=xpid, user=user, db=db)


def access(db: Session, user: User, xpid: int, kind: str, rid: int) -> Access:
    if kind not in KINDS:
        raise HTTPException(404, "Not found")
    if kind == "user" and rid == user.id:
        ctx = None
        if xpid:
            try:
                ctx = _ctx_for(db, user, xpid)
            except HTTPException:
                ctx = None
        return Access(user.name, user.name_bn, True, True, ctx)
    ctx = _ctx_for(db, user, xpid)
    prop = ctx.property
    if kind == "user":
        t = db.get(User, rid)
        ok = t and db.scalar(select(Membership.id).where(Membership.user_id == rid, Membership.org_id == prop.org_id,
                                                         (Membership.property_id == prop.id) | (Membership.property_id.is_(None))).limit(1))
        if not ok:
            raise HTTPException(404, "Not found")
        edit = ctx.has(*MANAGE)
        return Access(t.name, t.name_bn, edit or ctx.has(*SEE_CONTACTS), edit, ctx)
    if kind == "occupant":
        o = db.get(Occupancy, rid)
        u = db.get(Unit, o.unit_id) if o else None
        if not o or not u or u.property_id != prop.id:
            raise HTTPException(404, "Not found")
        own = o.user_id == user.id
        edit = own or ctx.has(*EDIT_OCC) or (ctx.has(*OWNERS) and o.unit_id in ctx.unit_ids)
        return Access(o.name, o.name_bn, edit or ctx.has(*SEE_CONTACTS), edit, ctx)
    s = db.get(Staff, rid)
    if not s or s.property_id != prop.id:
        raise HTTPException(404, "Not found")
    return Access(s.name, s.name_bn, ctx.has(*SEE_CONTACTS), ctx.has(*EDIT_OCC), ctx)


def _row(db: Session, kind: str, rid: int) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.kind == kind, Profile.ref_id == rid))


def _get_or_new(db: Session, kind: str, rid: int) -> Profile:
    p = _row(db, kind, rid)
    if not p:
        p = Profile(kind=kind, ref_id=rid, languages=[])
        db.add(p)
        db.flush()
    return p


def details(p: Profile | None) -> dict:
    return {"about": p.about if p else "", "dob": p.dob.isoformat() if p and p.dob else None, "blood_group": p.blood_group if p else "",
            "profession": p.profession if p else "", "emergency_name": p.emergency_name if p else "", "emergency_phone": p.emergency_phone if p else "",
            "address": p.address if p else "", "languages": list(p.languages or []) if p else []}


def payload(kind: str, rid: int, a: Access, p: Profile | None) -> dict:
    has = bool(p and p.photo_file)
    return {"kind": kind, "id": rid, "name": a.name, "name_bn": a.name_bn, "has_photo": has, "photo_ver": p.photo_ver if has else 0,
            "can_edit": a.edit, "can_see_details": a.see, "details": details(p) if a.see else None}


class DetailsIn(BaseModel):
    about: str = Field(default="", max_length=300)
    dob: date | None = None
    blood_group: str = ""
    profession: str = Field(default="", max_length=120)
    emergency_name: str = Field(default="", max_length=120)
    emergency_phone: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=240)
    languages: list[str] = Field(default_factory=list, max_length=8)


def _audit(db: Session, user: User, a: Access, action: str, kind: str, rid: int, meta: dict | None = None):
    c = a.ctx
    audit(db, user_id=user.id, org_id=c.property.org_id if c else None, property_id=c.property.id if c else None,
          action=action, entity=f"profile.{kind}", entity_id=rid, meta=meta or {})


@router.get("/photos")
def photo_index(x_property_id: int = Header(default=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Which people in the current building have a photo, with a version for cache busting. Cheap, loaded once per page."""
    out: dict = {"user": {}, "occupant": {}, "staff": {}}
    mine = _row(db, "user", user.id)
    if mine and mine.photo_file:
        out["user"][user.id] = mine.photo_ver
    ctx = None
    if x_property_id:
        try:
            ctx = _ctx_for(db, user, x_property_id)
        except HTTPException:
            ctx = None
    if not ctx:
        return out
    prop = ctx.property
    uids = {r for r in db.scalars(select(Membership.user_id).where(Membership.org_id == prop.org_id,
                                                                    (Membership.property_id == prop.id) | (Membership.property_id.is_(None))))}
    oids = {r for r in db.scalars(select(Occupancy.id).join(Unit, Unit.id == Occupancy.unit_id).where(Unit.property_id == prop.id))}
    sids = {r for r in db.scalars(select(Staff.id).where(Staff.property_id == prop.id))}
    for p in db.scalars(select(Profile).where(Profile.photo_file != "")):
        if (p.kind == "user" and p.ref_id in uids) or (p.kind == "occupant" and p.ref_id in oids) or (p.kind == "staff" and p.ref_id in sids):
            out[p.kind][p.ref_id] = p.photo_ver
    return out


@router.get("/{kind}/{rid}")
def read(kind: str, rid: int, x_property_id: int = Header(default=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = access(db, user, x_property_id, kind, rid)
    return payload(kind, rid, a, _row(db, kind, rid))


@router.put("/{kind}/{rid}")
def update(kind: str, rid: int, body: DetailsIn, x_property_id: int = Header(default=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = access(db, user, x_property_id, kind, rid)
    if not a.edit:
        raise HTTPException(403, "Your role cannot do this")
    if body.blood_group not in BLOOD:
        raise HTTPException(422, "Unknown blood group")
    if body.dob and body.dob > date.today():
        raise HTTPException(422, "Date of birth cannot be in the future")
    langs = [x.strip()[:30] for x in body.languages if x.strip()]
    p = _get_or_new(db, kind, rid)
    p.about, p.dob, p.blood_group, p.profession = body.about.strip(), body.dob, body.blood_group, body.profession.strip()
    p.emergency_name, p.emergency_phone, p.address = body.emergency_name.strip(), body.emergency_phone.strip(), body.address.strip()
    p.languages, p.updated_at = langs, now()
    _audit(db, user, a, "profile.update", kind, rid, {"fields": [k for k, v in body.model_dump().items() if v]})
    db.commit()
    return payload(kind, rid, a, p)


@router.post("/{kind}/{rid}/photo")
async def upload_photo(kind: str, rid: int, file: UploadFile = File(...), x_property_id: int = Header(default=0),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = access(db, user, x_property_id, kind, rid)
    if not a.edit:
        raise HTTPException(403, "Your role cannot do this")
    if file.content_type not in TYPES:
        raise HTTPException(422, "Please upload a JPG or PNG photo")
    data = await file.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "The photo is larger than 2 MB")
    real = sniff(data)
    if real != file.content_type:
        raise HTTPException(422, "The file is not a valid JPG or PNG photo")
    p = _get_or_new(db, kind, rid)
    old = p.photo_file
    name = f"{kind}_{rid}_{secrets.token_hex(6)}.{TYPES[real]}"
    (avatar_dir() / name).write_bytes(data)
    p.photo_file, p.photo_type, p.photo_ver, p.updated_at = name, real, (p.photo_ver or 0) + 1, now()
    if old:
        (avatar_dir() / old).unlink(missing_ok=True)
    _audit(db, user, a, "profile.photo", kind, rid, {"size": len(data), "type": real})
    db.commit()
    return payload(kind, rid, a, p)


@router.delete("/{kind}/{rid}/photo")
def delete_photo(kind: str, rid: int, x_property_id: int = Header(default=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = access(db, user, x_property_id, kind, rid)
    if not a.edit:
        raise HTTPException(403, "Your role cannot do this")
    p = _row(db, kind, rid)
    if p and p.photo_file:
        (avatar_dir() / p.photo_file).unlink(missing_ok=True)
        p.photo_file, p.photo_type, p.photo_ver = "", "", (p.photo_ver or 0) + 1
        _audit(db, user, a, "profile.photo.remove", kind, rid)
        db.commit()
    return payload(kind, rid, a, p)


@router.get("/{kind}/{rid}/photo")
def photo(kind: str, rid: int, v: int = 0, x_property_id: int = Header(default=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    access(db, user, x_property_id, kind, rid)
    p = _row(db, kind, rid)
    path = avatar_dir() / p.photo_file if p and p.photo_file else None
    if not path or not path.exists():
        raise HTTPException(404, "No photo")
    # The ?v= number changes with every new photo, so a day of private caching is safe.
    return FileResponse(path, media_type=p.photo_type, headers={"Cache-Control": "private, max-age=86400"})
