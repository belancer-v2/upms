"""cPanel "Setup Python App" (Passenger) entry point.

Passenger speaks WSGI; FlatWise is an ASGI (FastAPI) app, so a2wsgi adapts it. Passenger looks for the
name `application` in this file. Settings come from the environment variables set in the cPanel app
screen; as a fallback a `.env` file next to this file (KEY=value lines, chmod 600) is read, without
overriding variables that are already set.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key.strip(), val)


_load_dotenv(HERE / ".env")
os.environ.setdefault("ENV", "production")

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import app as asgi_app  # noqa: E402

application = ASGIMiddleware(asgi_app)
