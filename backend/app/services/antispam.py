"""Cheap, proof-of-work-free spam defence for the public forms.

Two signals: a honeypot field that real people never see (`hp`), and a signed form token (`ft`) that proves the form was loaded at least
MIN_SECONDS ago. In production (ANTISPAM_STRICT) the token is required; elsewhere it is checked only when sent. A failed check is answered
as if it worked, so a bot learns nothing, and nothing is stored.
"""
import time

from .. import config
from . import mailer as M

MIN_SECONDS = 3
MAX_SECONDS = 2 * 3600


def issue() -> str:
    return M.sign({"p": "form", "t": int(time.time())})


def looks_human(hp: str, ft: str) -> bool:
    if (hp or "").strip():
        return False
    if not ft:
        return not config.ANTISPAM_STRICT
    data = M.unsign(ft, "form")
    if not data:
        return False
    try:
        age = time.time() - int(data.get("t", 0))
    except (TypeError, ValueError):
        return False
    return MIN_SECONDS <= age <= MAX_SECONDS
