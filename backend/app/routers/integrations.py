import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import emailer
from ..database import get_db
from ..models import Leave, Onboarding, Task, User
from ..schemas import TestEmailIn
from ..security import current_user, require_roles
from ..services import my_employee

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


@router.get("/status")
def status(user: User = Depends(current_user)):
    return {"email_configured": emailer.configured(),
            "email_mode": "SMTP" if emailer.configured() else "Outbox log (storage/outbox.log)"}


@router.post("/test-email")
def test_email(body: TestEmailIn, user: User = Depends(require_roles("admin"))):
    ok, msg = emailer.send_sync(body.to or user.email, "WorkSphere test email",
                                "This is a test email from WorkSphere. Email integration is working.")
    if not ok:
        raise HTTPException(502, msg)
    return {"ok": True, "message": msg}


def _e(s) -> str:
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


@router.get("/calendar.ics")
def my_calendar(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """iCalendar file (works with Google Calendar, Outlook, Apple Calendar import)."""
    emp = my_employee(db, user)
    if not emp:
        raise HTTPException(400, "No employee profile is linked to this account")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WorkSphere//HRMS//EN", "CALSCALE:GREGORIAN"]

    def event(uid, start: dt.date, end_inclusive: dt.date, summary, desc=""):
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}@worksphere", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{end_inclusive + dt.timedelta(days=1):%Y%m%d}",
                      f"SUMMARY:{_e(summary)}", f"DESCRIPTION:{_e(desc)}", "END:VEVENT"])

    for l in db.scalars(select(Leave).where(Leave.employee_id == emp.id, Leave.status.in_(("approved", "pending")))):
        event(f"leave-{l.id}", l.start_date, l.end_date, f"{l.leave_type} leave ({l.status})", l.reason)
    for t in db.scalars(select(Task).where(Task.assigned_to == emp.id, Task.status == "pending", Task.due_date.is_not(None))):
        event(f"task-{t.id}", t.due_date, t.due_date, f"Task due: {t.title}", t.description)
    for o in db.scalars(select(Onboarding).where(Onboarding.employee_id == emp.id, Onboarding.status == "pending",
                                                 Onboarding.due_date.is_not(None))):
        event(f"onb-{o.id}", o.due_date, o.due_date, f"Onboarding due: {o.task_name}")
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="worksphere-calendar.ics"'})
