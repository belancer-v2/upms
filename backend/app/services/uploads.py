"""Shared upload checks: what the bytes really are, a safe display name, and a download response that can never run in a browser."""
import re
import unicodedata

from fastapi import HTTPException

# Magic numbers of the only formats the app accepts.
SIGNATURES = (("image/png", b"\x89PNG\r\n\x1a\n"), ("image/jpeg", b"\xff\xd8\xff"), ("application/pdf", b"%PDF-"))
EXT = {"image/png": "png", "image/jpeg": "jpg", "application/pdf": "pdf"}


def sniff(data: bytes) -> str | None:
    """The real type from the first bytes, whatever the client claimed."""
    head = data[:16]
    for mime, sig in SIGNATURES:
        if head.startswith(sig):
            return mime
    return None


def check(data: bytes, claimed: str | None, allowed: set[str] | frozenset[str]) -> str:
    """Returns the real mime type, or raises 422. The claimed content type and the bytes must agree and be on the allow-list."""
    real = sniff(data)
    if real is None or real not in allowed or (claimed or "") != real:
        raise HTTPException(422, "The file is not a valid " + ("photo or PDF" if "application/pdf" in allowed else "JPG or PNG photo") + ".")
    return real


_BAD = re.compile(r"[\x00-\x1f\x7f\"'<>|:*?\\/;`$&{}\[\]^%]")


def safe_filename(name: str | None, fallback: str = "file") -> str:
    """A display name only (storage keys are always random): no path parts, control characters, quotes or leading dots, at most 120 characters."""
    n = unicodedata.normalize("NFC", (name or "").replace("\\", "/").split("/")[-1])
    n = _BAD.sub("_", n).strip(" .")[:120]
    return n or fallback
