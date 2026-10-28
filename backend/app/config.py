import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"


def _load_env():
    # First run: create .env with a random signing key (never hard-coded).
    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"SECRET_KEY={secrets.token_urlsafe(48)}\nADMIN_EMAIL=admin@worksphere.com\nADMIN_PASSWORD=Admin@123\nADMIN_NAME=Aarav Sharma\n", encoding="utf-8")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _int(name, default):
    return int(os.environ.get(name, default))


class Settings:
    secret_key = os.environ["SECRET_KEY"]
    algorithm = "HS256"
    token_minutes = _int("TOKEN_MINUTES", 480)
    grace_minutes = _int("GRACE_MINUTES", 10)              # late after shift start + grace
    early_window_minutes = _int("EARLY_WINDOW_MINUTES", 30)  # "early" check-in window
    leave_conflict_limit = _int("LEAVE_CONFLICT_LIMIT", 2)   # max people of a dept on leave per day
    max_upload_mb = _int("MAX_UPLOAD_MB", 5)
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT / 'worksphere.db'}")
    storage_dir = ROOT / "storage" / "documents"
    frontend_dir = ROOT / "frontend"
    default_password = "Welcome@123"
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port = _int("SMTP_PORT", 587)
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", "WorkSphere <no-reply@worksphere.local>")
    smtp_tls = os.environ.get("SMTP_TLS", "1") == "1"
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@worksphere.com").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    admin_name = os.environ.get("ADMIN_NAME", "Aarav Sharma")


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
