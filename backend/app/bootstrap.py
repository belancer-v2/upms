"""One command for a new production install:   python -m app.bootstrap

1. runs `alembic upgrade head` (the only way the production schema is created),
2. loads reference data (plans, credit packs, platform settings), only rows that are missing,
3. creates the first SUPER_ADMIN from BOOTSTRAP_ADMIN_EMAIL / _NAME / _PASSWORD (skipped when a SUPER_ADMIN exists).

Safe to run again. It never loads demo data.  Use `--no-migrate` to skip step 1, `--check` to only print what would happen.
"""
import os
import sys
from pathlib import Path

from sqlalchemy import select

from . import config, prodcheck

BACKEND = Path(__file__).resolve().parent.parent


def migrate() -> None:
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")


def reference_data(db) -> list[str]:
    from .models.credits import CreditPack, PlatformSetting
    from .models.saas import Plan
    from .seed import plan_catalogue
    from .seed_credits import EMAIL_INCLUDED, PACKS
    done = []
    have = {p.key for p in db.scalars(select(Plan))}
    for p in plan_catalogue():
        if p.key not in have:
            p.email_included = EMAIL_INCLUDED.get(p.key, {})
            db.add(p)
            done.append(f"plan {p.key}")
    if not db.scalar(select(CreditPack.id).limit(1)):
        for n, (kind, name, bn, credits, price) in enumerate(PACKS):
            db.add(CreditPack(kind=kind, name=name, name_bn=bn, credits=credits, price=price, sort=n))
        done.append("credit packs")
    have_s = {s.key for s in db.scalars(select(PlatformSetting))}
    for key, val in (("vat_bps", "0"), ("pay_bkash", ""), ("pay_nagad", ""), ("pay_bank", "")):  # payment instructions are filled in from the SaaS console
        if key not in have_s:
            db.add(PlatformSetting(key=key, value=val))
            done.append(f"setting {key}")
    return done


def first_admin(db) -> str:
    from .models.core import User
    from .security import hash_password
    if db.scalar(select(User.id).where(User.saas_role == "SUPER_ADMIN").limit(1)):
        return "a SUPER_ADMIN already exists; nothing created"
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    name = os.getenv("BOOTSTRAP_ADMIN_NAME", "").strip() or "Super Admin"
    pw = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if "@" not in email or len(pw) < 12:
        raise SystemExit("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD (12+ characters) to create the first SUPER_ADMIN.")
    db.add(User(email=email, name=name, password_hash=hash_password(pw), saas_role="SUPER_ADMIN", phone=""))
    return f"created SUPER_ADMIN {email}"


def main(argv: list[str]) -> int:
    prodcheck.enforce()
    if "--check" in argv:
        print("config ok" if not config.PRODUCTION or not prodcheck.problems() else prodcheck.problems())
        return 0
    if "--no-migrate" not in argv:
        print("running migrations ...", flush=True)
        migrate()
    from .db import SessionLocal
    with SessionLocal() as db:
        for line in reference_data(db):
            print("loaded", line)
        print(first_admin(db))
        db.commit()
    print("bootstrap done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
