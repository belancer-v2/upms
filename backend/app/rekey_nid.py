"""Re-encrypt every encrypted NID column with a new key (NID_KEY rotation).

    OLD_NID_KEY=<current key> NEW_NID_KEY=<new key> python -m app.rekey_nid --dry-run     # decrypts everything, changes nothing
    OLD_NID_KEY=<current key> NEW_NID_KEY=<new key> python -m app.rekey_nid               # does it, in one transaction

Every column whose name ends in `_enc` is processed (staff, tenant cases, agency staff). Stop the API (or put it in
maintenance) while this runs, then deploy with NID_KEY=<new key>. Back up the database first (scripts/backup.sh).
An empty OLD_NID_KEY means the data was written with the development key derived from SECRET_KEY (set SECRET_KEY to the one used then).
"""
import base64
import hashlib
import os
import sys

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update

from . import models  # noqa: F401
from .db import Base, SessionLocal


def _fernet(key: str, secret: str) -> Fernet:
    return Fernet(key.encode() if key else base64.urlsafe_b64encode(hashlib.sha256(("nid:" + secret).encode()).digest()))


def rekey(db, old: Fernet, new: Fernet, dry_run: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        pk = list(table.primary_key.columns)
        for col in table.columns:
            if not col.name.endswith("_enc"):
                continue
            n = 0
            for row in db.execute(select(*pk, col).where(col != "")).all():
                *ids, blob = row
                try:
                    plain = old.decrypt(blob.encode())
                except InvalidToken:
                    raise SystemExit(f"{table.name}.{col.name} id={ids}: cannot decrypt with OLD_NID_KEY. Nothing was changed.")
                if not dry_run:
                    db.execute(update(table).where(*[c == v for c, v in zip(pk, ids)]).values({col.name: new.encrypt(plain).decode()}))
                n += 1
            counts[f"{table.name}.{col.name}"] = n
    return counts


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    secret = os.getenv("SECRET_KEY", "dev-only-change-me-flatwise-secret-key-32b")
    new_key = os.getenv("NEW_NID_KEY", "")
    if not new_key:
        raise SystemExit("Set NEW_NID_KEY (python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")")
    old, new = _fernet(os.getenv("OLD_NID_KEY", ""), secret), _fernet(new_key, secret)
    with SessionLocal() as db:
        counts = rekey(db, old, new, dry)
        if dry:
            db.rollback()
        else:
            db.commit()
    for k, v in counts.items():
        print(f"{'would re-encrypt' if dry else 're-encrypted'} {v:6d}  {k}")
    print("dry run only, nothing changed" if dry else "done. Now deploy with NID_KEY set to the new key.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
