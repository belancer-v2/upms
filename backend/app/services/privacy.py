"""Erasing a person's details (account deletion) without breaking the books.

What stays: invoices, payments, journal lines, expenses and the audit log. They point to flats and to numeric user ids, never to a name, so
the ledger still balances. What goes: the person's name, email, phone, photo, profile details, sign-in and sessions.
"""
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..models.core import Membership, User, now


def blockers(db: Session, user: User) -> list[str]:
    """Reasons this account cannot be erased yet. Empty list = ok."""
    out = []
    if user.saas_role:
        out.append("saas_staff")   # FlatWise staff accounts are closed by a super admin from the team page
    for m in db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.role == "PROPERTY_ADMIN")):
        others = db.scalar(select(Membership.id).where(Membership.org_id == m.org_id, Membership.role == "PROPERTY_ADMIN", Membership.user_id != user.id))
        if not others:
            out.append("last_admin")   # the building would be left with nobody to run it
            break
    return out


def anonymise_user(db: Session, user: User, by_user_id: int | None = None) -> dict:
    """Blank the personal details of one user and close the sign-in. The caller commits. Safe to call twice."""
    from ..models.amenities import Booking
    from ..models.notice import Receipt
    from ..models.parking import Vehicle
    from ..models.profile import Profile
    from ..models.property import Occupancy
    from ..models.requests import CommitteeMember
    from ..models.security import AuthSession, AuthToken
    uid, done = user.id, {}
    label = f"Deleted user {uid}"
    # profile row and photo
    prof = db.scalar(select(Profile).where(Profile.kind == "user", Profile.ref_id == uid))
    if prof:
        if prof.photo_file:
            (config.UPLOAD_DIR / "avatars" / prof.photo_file).unlink(missing_ok=True)
        db.delete(prof)
        done["profile"] = 1
    # people records linked to this login
    occ = list(db.scalars(select(Occupancy).where(Occupancy.user_id == uid)))
    for o in occ:
        o.name, o.name_bn, o.phone, o.email = "Former resident", "", "", ""
        o.user_id = None
    done["occupancies"] = len(occ)
    cm = list(db.scalars(select(CommitteeMember).where(CommitteeMember.user_id == uid)))
    for c in cm:
        c.name, c.name_bn, c.note, c.user_id = "Former member", "", "", None
    done["committee_members"] = len(cm)
    rc = db.execute(update(Receipt).where(Receipt.user_id == uid).values(name="", phone="", user_id=None)).rowcount
    done["notice_receipts"] = rc or 0
    db.execute(update(Vehicle).where(Vehicle.registered_by == uid).values(registered_by=None))
    db.execute(update(Booking).where(Booking.user_id == uid).values(contact=""))
    # sign-in
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == uid, AuthSession.revoked_at.is_(None))):
        s.revoked_at, s.revoked_reason = now(), "account_deleted"
    for t in db.scalars(select(AuthToken).where(AuthToken.user_id == uid, AuthToken.used_at.is_(None))):
        t.used_at = now()
    for m in db.scalars(select(Membership).where(Membership.user_id == uid)):
        db.delete(m)
    user.name, user.name_bn, user.phone = label, "", ""
    user.email = f"deleted-{uid}@deleted.invalid"
    user.password_hash = "!" + secrets.token_hex(24)     # not a bcrypt hash, so no password can ever match
    user.is_active = False
    user.token_version = (user.token_version or 0) + 1
    audit(db, user_id=by_user_id, action="privacy.anonymise", entity="user", entity_id=uid, meta=done)
    return done
