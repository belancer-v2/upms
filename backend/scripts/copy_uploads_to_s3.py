"""Copy existing local uploads (UPLOAD_DIR) into the S3 bucket. Safe to run again: files already there with the same size are skipped.

    cd backend && STORAGE_BACKEND=s3 S3_BUCKET=... S3_ENDPOINT_URL=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... python scripts/copy_uploads_to_s3.py [--dry-run] [--delete-local]

Keys keep the same relative path, so nothing in the database changes. --delete-local removes a local file only after the upload was verified.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def copy(src, dst, dry_run: bool = False, delete_local: bool = False, log=print) -> dict:
    stats = {"copied": 0, "skipped": 0, "failed": 0, "deleted": 0}
    for key in src.iter_keys():
        try:
            data = src.get(key)
            if dst.exists(key) and len(dst.get(key)) == len(data):
                stats["skipped"] += 1
            elif dry_run:
                log(f"would copy {key}")
                stats["copied"] += 1
                continue
            else:
                dst.put(key, data)
                if dst.get(key) != data:
                    raise IOError("verification failed")
                stats["copied"] += 1
            if delete_local and not dry_run:
                src.delete(key)
                stats["deleted"] += 1
        except Exception as e:
            stats["failed"] += 1
            log(f"FAILED {key}: {type(e).__name__}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delete-local", action="store_true")
    a = ap.parse_args()
    os.environ["STORAGE_BACKEND"] = "s3"
    from app import config
    from app.services.storage import LocalStorage, get_storage
    st = copy(LocalStorage(config.UPLOAD_DIR), get_storage(), a.dry_run, a.delete_local)
    print(st)
    return 1 if st["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
