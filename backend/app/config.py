import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'flatwise.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-flatwise-secret-key-32b")
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "24"))
# DEMO=1 shows demo accounts on the login screen and allows seeding. Never enable in production.
DEMO = os.getenv("DEMO", "1") == "1"
# Key used to encrypt NID numbers at rest (Fernet needs a urlsafe base64 32-byte key).
NID_KEY = os.getenv("NID_KEY", "")
