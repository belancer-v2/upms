"""Staff register, the NID vault, and monthly payroll."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Message
from ..models.core import User
from ..models.agency import StaffPosting, posting_map
from ..models.staff import NidView, SalaryLine, SalarySheet, Staff
from ..permissions import COMMITTEE, MANAGE
from ..services import ledger, vault
from ..services.messaging import deliver

router = APIRouter(prefix="/api/staff", tags=["staff"])
VIEW = MANAGE | COMMITTEE | {"AUDITOR"}
EDIT = MANAGE | {"SECRETARY"}
PREPARE = MANAGE | {"TREASURER"}
APPROVE = MANAGE | {"PRESIDENT"}
REVEAL = MANAGE | {"PRESIDENT"}
ROLES = "^(caretaker|guard|cleaner|driver|other)$"


def _gate(ctx: Ctx):
    ctx.feature("staff")


def _s(s: Staff) -> dict:
    return {"id": s.id, "name": s.name, "name_bn": s.name_bn, "role": s.role, "phone": s.phone, "joined": s.joined.isoformat(), "salary": s.salary, "status": s.status,
            "nid": vault.mask(s.nid_last4), "has_nid": bool(s.nid_enc)}


class StaffIn(BaseModel):
    name: str = Field(min_length=2)
    name_bn: str = ""
    role: str = Field(default="other", pattern=ROLES)
    phone: str = ""
    joined: date | None = None
    salary: int = Field(ge=0)
    nid: str = Field(default="", max_length=20)


@router.get("")
def staff(employer: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*VIEW)
    links = posting_map(db, ctx.property.id)
    rows = [{**_s(s), "agency": links.get(s.id)} for s in db.scalars(select(Staff).where(Staff.property_id == ctx.property.id).order_by(Staff.status, Staff.role, Staff.name))]
    if employer == "all":   # default is the building's own staff; agency staff are listed on request (M18)
        return rows
    if employer.isdigit():
        return [r for r in rows if r["agency"] and r["agency"]["agency_id"] == int(employer)]
    return [r for r in rows if not r["agency"]]


@router.post("", status_code=201)
def add(body: StaffIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*EDIT)
    nid = "".join(ch for ch in body.nid if ch.isdigit())
    if body.nid and len(nid) not in (10, 13, 17):
        raise HTTPException(422, "A National ID has 10, 13 or 17 digits")
    s = Staff(property_id=ctx.property.id, name=body.name, name_bn=body.name_bn, role=body.role, phone=body.phone, joined=body.joined or date.today(), salary=body.salary,
              nid_enc=vault.seal(nid) if nid else "", nid_last4=nid[-4:] if nid else "")
    db.add(s)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="staff.add", entity="staff", entity_id=s.id, meta={"role": s.role})
    db.commit()
    return _s(s)


@router.put("/{sid}")
def edit(sid: int, body: StaffIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*EDIT)
    s = db.get(Staff, sid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    nid = "".join(ch for ch in body.nid if ch.isdigit())
    if body.nid and len(nid) not in (10, 13, 17):
        raise HTTPException(422, "A National ID has 10, 13 or 17 digits")
    s.name, s.name_bn, s.role, s.phone, s.salary = body.name, body.name_bn, body.role, body.phone, body.salary
    if nid:
        s.nid_enc, s.nid_last4 = vault.seal(nid), nid[-4:]
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="staff.edit", entity="staff", entity_id=s.id, meta={"salary": s.salary})
    db.commit()
    return _s(s)


@router.post("/{sid}/leave")
def leave(sid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*EDIT)
    s = db.get(Staff, sid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    s.status = "left"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="staff.leave", entity="staff", entity_id=s.id)
    db.commit()
    return _s(s)


@router.post("/{sid}/reveal-nid")
def reveal(sid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Shows the full NID once and writes who looked, and when."""
    _gate(ctx)
    ctx.need(*REVEAL)
    s = db.get(Staff, sid)
    if not s or s.property_id != ctx.property.id or not s.nid_enc:
        raise HTTPException(404, "Not found")
    db.add(NidView(property_id=ctx.property.id, staff_id=s.id, viewer_id=ctx.user.id))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="staff.nid.view", entity="staff", entity_id=s.id)
    db.commit()
    return {"nid": vault.unseal(s.nid_enc)}


@router.get("/{sid}/nid-views")
def nid_views(sid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(REVEAL | {"AUDITOR"}))
    users = {u.id: u.name for u in db.scalars(select(User))}
    return [{"viewer": users.get(v.viewer_id, ""), "at": v.at.isoformat()} for v in db.scalars(select(NidView).where(NidView.staff_id == sid, NidView.property_id == ctx.property.id).order_by(NidView.id.desc()).limit(50))]


# ---------------- payroll
def _line(l: SalaryLine, st: dict) -> dict:
    s = st.get(l.staff_id)
    return {"id": l.id, "staff_id": l.staff_id, "name": s.name if s else "", "name_bn": s.name_bn if s else "", "role": s.role if s else "", "base": l.base, "bonus": l.bonus, "deduction": l.deduction,
            "net": l.base + l.bonus - l.deduction, "bonus_kind": l.bonus_kind, "note": l.note}


def _sheet(db: Session, sh: SalarySheet, ctx: Ctx, lines: bool = True) -> dict:
    st = {s.id: s for s in db.scalars(select(Staff).where(Staff.property_id == ctx.property.id))}
    ls = db.scalars(select(SalaryLine).where(SalaryLine.sheet_id == sh.id).order_by(SalaryLine.id)).all()
    users = {u.id: u.name for u in db.scalars(select(User))}
    d = {"id": sh.id, "period": sh.period, "status": sh.status, "total": sum(l.base + l.bonus - l.deduction for l in ls), "people": len(ls), "created_by": users.get(sh.created_by, ""), "created_by_id": sh.created_by,
         "approved_by": users.get(sh.approved_by, "") if sh.approved_by else "", "paid_on": sh.paid_on.isoformat() if sh.paid_on else None, "method": sh.method}
    if lines:
        d["lines"] = [_line(l, st) for l in ls]
    return d


@router.get("/payroll/sheets")
def sheets(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*VIEW)
    return [_sheet(db, sh, ctx, lines=False) for sh in db.scalars(select(SalarySheet).where(SalarySheet.property_id == ctx.property.id).order_by(SalarySheet.period.desc()))]


@router.get("/payroll/sheets/{shid}")
def sheet(shid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*VIEW)
    return _sheet(db, _own(db, ctx, shid), ctx)


def _own(db: Session, ctx: Ctx, shid: int) -> SalarySheet:
    sh = db.get(SalarySheet, shid)
    if not sh or sh.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return sh


class NewSheet(BaseModel):
    period: str


@router.post("/payroll/sheets", status_code=201)
def new_sheet(body: NewSheet, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*PREPARE)
    p = body.period
    if not (len(p) == 7 and p[4] == "-" and p[:4].isdigit() and p[5:].isdigit() and 1 <= int(p[5:]) <= 12):
        raise HTTPException(422, "Period must look like 2026-10")
    if db.scalar(select(SalarySheet.id).where(SalarySheet.property_id == ctx.property.id, SalarySheet.period == p)):
        raise HTTPException(409, "A salary sheet for this month already exists")
    people = db.scalars(select(Staff).where(Staff.property_id == ctx.property.id, Staff.status == "active", Staff.id.not_in(select(StaffPosting.staff_id)))).all()   # agency staff are paid by their agency
    if not people:
        raise HTTPException(422, "Add staff first")
    sh = SalarySheet(property_id=ctx.property.id, period=p, created_by=ctx.user.id)
    db.add(sh)
    db.flush()
    for s in people:
        db.add(SalaryLine(sheet_id=sh.id, staff_id=s.id, base=s.salary))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="payroll.create", entity="sheet", entity_id=sh.id, meta={"period": p, "people": len(people)})
    db.commit()
    return _sheet(db, sh, ctx)


class LineIn(BaseModel):
    bonus: int = Field(default=0, ge=0)
    deduction: int = Field(default=0, ge=0)
    note: str = ""


@router.put("/payroll/lines/{lid}")
def edit_line(lid: int, body: LineIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*PREPARE)
    l = db.get(SalaryLine, lid)
    sh = db.get(SalarySheet, l.sheet_id) if l else None
    if not l or sh.property_id != ctx.property.id or sh.status != "draft":
        raise HTTPException(422, "Only a draft sheet can be changed")
    if body.deduction > l.base + body.bonus:
        raise HTTPException(422, "Deduction is more than the pay")
    l.bonus, l.deduction, l.note = body.bonus, body.deduction, body.note[:120]
    l.bonus_kind = "other" if body.bonus and l.bonus_kind != "eid" else l.bonus_kind
    db.commit()
    return _sheet(db, sh, ctx)


class EidIn(BaseModel):
    percent: int = Field(ge=1, le=200)


@router.post("/payroll/sheets/{shid}/eid-bonus")
def eid(shid: int, body: EidIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Adds an Eid bonus of a percent of base pay to everyone on the sheet. Running it again replaces it, never doubles it."""
    _gate(ctx)
    ctx.need(*PREPARE)
    sh = _own(db, ctx, shid)
    if sh.status != "draft":
        raise HTTPException(422, "Only a draft sheet can be changed")
    for l in db.scalars(select(SalaryLine).where(SalaryLine.sheet_id == sh.id)):
        l.bonus, l.bonus_kind = round(l.base * body.percent / 100 / 100) * 100, "eid"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="payroll.eid", entity="sheet", entity_id=sh.id, meta={"percent": body.percent})
    db.commit()
    return _sheet(db, sh, ctx)


@router.post("/payroll/sheets/{shid}/approve")
def approve(shid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*APPROVE)
    sh = _own(db, ctx, shid)
    if sh.status != "draft":
        raise HTTPException(422, "Already approved")
    if sh.created_by == ctx.user.id:
        raise HTTPException(403, "You cannot approve a sheet you prepared")
    sh.status, sh.approved_by = "approved", ctx.user.id
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="payroll.approve", entity="sheet", entity_id=sh.id)
    db.commit()
    return _sheet(db, sh, ctx)


class PayIn(BaseModel):
    method: str = Field(pattern="^(cash|bank|bkash|nagad)$")


@router.post("/payroll/sheets/{shid}/pay")
def pay(shid: int, body: PayIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Marks the month paid, writes one ledger entry, and sends each person a payslip SMS."""
    _gate(ctx)
    ctx.need(*PREPARE)
    sh = _own(db, ctx, shid)
    if sh.status != "approved":
        raise HTTPException(422, "Approve the sheet first")
    lines = db.scalars(select(SalaryLine).where(SalaryLine.sheet_id == sh.id)).all()
    total = sum(l.base + l.bonus - l.deduction for l in lines)
    sh.status, sh.paid_on, sh.method = "paid", date.today(), body.method
    ledger.post(db, sh.property_id, sh.paid_on, f"Salaries {sh.period}", [("5030", total, 0), (ledger.METHOD_ACCOUNT[body.method], 0, total)], "payroll", sh.id, ctx.user.id)
    sent = failed = 0
    for l in lines:
        s = db.get(Staff, l.staff_id)
        net = l.base + l.bonus - l.deduction
        m = Message(property_id=ctx.property.id, to_name=s.name_bn or s.name, to_phone=s.phone, template="payslip", lang="bn", idem_key=f"payslip{l.id}",
                    body=f"{ctx.property.name_bn or ctx.property.name}: {sh.period} মাসের বেতন BDT {net / 100:,.0f} পরিশোধ করা হয়েছে।")
        db.add(m)
        deliver(db, ctx.property.org_id, m)
        sent += m.status == "sent"
        failed += m.status == "failed"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="payroll.pay", entity="sheet", entity_id=sh.id, meta={"total": total, "method": body.method})
    db.commit()
    return {**_sheet(db, sh, ctx), "sms_sent": sent, "sms_failed": failed}


@router.get("/payroll/lines/{lid}/payslip")
def payslip(lid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(MANAGE | {"TREASURER", "PRESIDENT"}))
    l = db.get(SalaryLine, lid)
    sh = db.get(SalarySheet, l.sheet_id) if l else None
    if not l or sh.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    s = db.get(Staff, l.staff_id)
    return {"building": ctx.property.name, "building_bn": ctx.property.name_bn, "address": ctx.property.address, "period": sh.period, "status": sh.status, "paid_on": sh.paid_on.isoformat() if sh.paid_on else None,
            "staff_id": s.id, "name": s.name, "name_bn": s.name_bn, "role": s.role, "base": l.base, "bonus": l.bonus, "bonus_kind": l.bonus_kind, "deduction": l.deduction, "net": l.base + l.bonus - l.deduction, "note": l.note, "method": sh.method}
