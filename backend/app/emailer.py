"""Email integration. Uses SMTP when SMTP_HOST is set; otherwise writes to storage/outbox.log (dev mode)."""
import datetime as dt
import smtplib
import threading
from email.message import EmailMessage

from .config import settings


def configured() -> bool:
    return bool(settings.smtp_host)


def _log(note: str, to: str, subject: str):
    path = settings.storage_dir.parent / "outbox.log"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {note} to={to} subject={subject}\n")


def send_sync(to: str, subject: str, body: str):
    subject = " ".join(subject.split())  # strip newlines: prevents header injection
    if not configured():
        _log("OUTBOX (SMTP not configured)", to, subject)
        return True, "SMTP is not configured, so the email was written to storage/outbox.log"
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            if settings.smtp_tls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True, "Email sent"
    except Exception as exc:  # network/auth errors must never break the request
        _log("FAILED " + str(exc)[:120], to, subject)
        return False, f"Email failed: {exc}"


def send_async(to: str, subject: str, body: str):
    threading.Thread(target=send_sync, args=(to, subject, body), daemon=True).start()
