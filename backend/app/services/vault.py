"""Encrypts NID numbers at rest. The key comes from NID_KEY, or is derived from SECRET_KEY in development."""
import base64
import hashlib

from cryptography.fernet import Fernet

from .. import config


def _fernet() -> Fernet:
    key = config.NID_KEY.encode() if config.NID_KEY else base64.urlsafe_b64encode(hashlib.sha256(("nid:" + config.SECRET_KEY).encode()).digest())
    return Fernet(key)


def seal(nid: str) -> str:
    return _fernet().encrypt(nid.encode()).decode()


def unseal(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode() if blob else ""


def mask(last4: str) -> str:
    return f"••••••{last4}" if last4 else ""
