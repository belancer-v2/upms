"""Client address behind a reverse proxy.

X-Forwarded-For is only believed when the direct peer is in TRUSTED_PROXIES (IPs or CIDRs). The header is read from the right: the first
address that is not a trusted proxy is the client. A spoofed left-most entry is therefore ignored.
"""
import ipaddress
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def _nets():
    out = []
    for p in config.TRUSTED_PROXIES:
        try:
            out.append(ipaddress.ip_network(p, strict=False))
        except ValueError:
            continue
    return tuple(out)


def _trusted(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in n for n in _nets())


def client_ip_from(peer: str, forwarded: str) -> str:
    peer = peer or ""
    if not _nets() or not _trusted(peer):
        return peer[:45]
    for part in reversed([x.strip() for x in (forwarded or "").split(",") if x.strip()]):
        try:
            ipaddress.ip_address(part)
        except ValueError:
            return peer[:45]  # malformed header: do not guess
        if not _trusted(part):
            return part[:45]
    return peer[:45]


def client_ip(request) -> str:
    peer = request.client.host if request.client else ""
    return client_ip_from(peer, request.headers.get("x-forwarded-for", ""))
