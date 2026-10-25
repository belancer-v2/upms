import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """cPanel cron jobs and SSH shells do not get the variables set in the Python App screen, so a chmod 600 `.env` next to
    the code is read too. Variables that are already set always win. Skipped when FLATWISE_NO_DOTENV=1 (tests)."""
    if os.getenv("FLATWISE_NO_DOTENV") == "1" or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.split(" #")[0].strip() if not val.strip()[:1] in "\"'" else val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key.strip(), val)


_load_dotenv(BASE_DIR / ".env")

# ENV=production turns on the startup safety checks in app/prodcheck.py and disables demo features.
ENV = os.getenv("ENV", "development").strip().lower()
PRODUCTION = ENV == "production"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'flatwise.db'}")
# Hosts hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg 3 driver name.
for _old in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_old):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_old):]
# cPanel hosts give MySQL/MariaDB: mysql://user:pass@localhost/db -> PyMySQL driver, utf8mb4 (Bangla text needs it).
for _old in ("mysql://", "mariadb://"):
    if DATABASE_URL.startswith(_old):
        DATABASE_URL = "mysql+pymysql://" + DATABASE_URL[len(_old):]
if DATABASE_URL.startswith("mysql") and "charset=" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "charset=utf8mb4"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-flatwise-secret-key-32b")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "24"))
# DEMO=1 shows demo accounts on the login screen and allows seeding. Never enable in production.
DEMO = os.getenv("DEMO", "0" if PRODUCTION else "1") == "1"
# Key used to encrypt NID numbers at rest (Fernet needs a urlsafe base64 32-byte key).
NID_KEY = os.getenv("NID_KEY", "")

# Uploaded tenant documents (NID photos, agreements). Use a private bucket in production.
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
MAX_UPLOAD_BYTES = 3 * 1024 * 1024

# Comma separated browser origins allowed to call the API cross-site. Empty = same-origin only (the web app proxies /api).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if PRODUCTION else "text").lower()

# ---- Security (P2). Every value can be overridden by an environment variable; see SECURITY.md.
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))     # short-lived bearer token
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))         # rotating refresh token, stored hashed
REFRESH_COOKIE = os.getenv("REFRESH_COOKIE", "1") == "1"                # also set the refresh token as an HttpOnly SameSite=Lax cookie
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "30"))
VERIFY_TOKEN_HOURS = int(os.getenv("VERIFY_TOKEN_HOURS", "48"))
# Proxies whose X-Forwarded-For is believed (comma separated IPs or CIDRs). Empty = use the socket address.
TRUSTED_PROXIES = [p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()]
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(2 * 1024 * 1024)))  # JSON / form bodies; multipart uploads get MAX_UPLOAD_BYTES + 1 MB
# Email verification before a signup can sign in (the 30 day trial starts at verification). On by default in production.
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "1" if PRODUCTION else "0") == "1"
# Signed form token + minimum fill time on the public forms. On by default in production.
ANTISPAM_STRICT = os.getenv("ANTISPAM_STRICT", "1" if PRODUCTION else "0") == "1"
# The sandbox payment provider lets the signed-in payer sign their own "success" callback. It must never be reachable in production.
SANDBOX_PAYMENTS = os.getenv("SANDBOX_PAYMENTS", "1" if DEMO else "0") == "1" and not PRODUCTION
RATE_LIMITS = os.getenv("RATE_LIMITS", "1") == "1"
