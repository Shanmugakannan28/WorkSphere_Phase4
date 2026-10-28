import datetime as dt
import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import emailer
from .config import settings
from .models import (Attendance, Document, Employee, EmployeeShift, Leave, LeaveBalance,
                     LeavePolicy, Notification, Performance, User)


# ---------- scoping / access ----------
def my_employee(db: Session, user: User):
    return db.scalar(select(Employee).where(Employee.user_id == user.id))


def scope_ids(db: Session, user: User):
    """None = everyone (admin/hr). Otherwise list of employee ids the user may see."""
    if user.role in ("admin", "hr"):
        return None
    me = my_employee(db, user)
    if not me:
        return []
    ids = [me.id]
    if user.role == "manager":
        ids += list(db.scalars(select(Employee.id).where(Employee.manager_id == me.id)))
    return ids


def ensure_access(db: Session, user: User, employee_id: int):
    ids = scope_ids(db, user)
    if ids is not None and employee_id not in ids:
        raise HTTPException(403, "You cannot access this employee's data")


def unique_username(db: Session, base: str) -> str:
    base = re.sub(r"[^a-z0-9_.-]", "", base.lower()) or "user"
    base = (base + "000")[:30]
    name, i = base, 1
    while db.scalar(select(User.id).where(User.username == name)):
        i += 1
        name = f"{base}{i}"
    return name


# ---------- notifications ----------
def notify(db: Session, user_id: int, title: str, message: str, kind: str = "info"):
    """In-app + optional email alert, honouring the user's notification preferences."""
    u = db.get(User, user_id)
    if u is not None:
        if kind in {t for t in (u.muted_types or "").split(",") if t}:
            return
        if u.pref_email:
            emailer.send_async(u.email, f"[WorkSphere] {title}", message)
        if not u.pref_inapp:
            return
    db.add(Notification(user_id=user_id, title=title, message=message, type=kind))


def notify_hr(db: Session, title: str, message: str, kind: str = "info"):
    for uid in db.scalars(select(User.id).where(User.role.in_(("hr", "admin")), User.is_active == True)):  # noqa: E712
        notify(db, uid, title, message, kind)


def manager_user_id(db: Session, emp: Employee):
    if not emp.manager_id:
        return None
    mgr = db.get(Employee, emp.manager_id)
    return mgr.user_id if mgr else None


# ---------- dates ----------
def workdays(start: dt.date, end: dt.date) -> int:
    n, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return n


def on_leave_ids(db: Session, day: dt.date) -> set:
    rows = db.scalars(select(Leave.employee_id).where(
        Leave.status == "approved", Leave.start_date <= day, Leave.end_date >= day))
    return set(rows)


# ---------- shifts & attendance ----------
def shift_of(db: Session, employee_id: int):
    es = db.scalar(select(EmployeeShift).where(EmployeeShift.employee_id == employee_id))
    return es.shift if es else None


def is_overnight(shift) -> bool:
    return shift.end_time <= shift.start_time


def shift_window(shift, day: dt.date):
    start = dt.datetime.combine(day, shift.start_time)
    end = dt.datetime.combine(day, shift.end_time)
    if end <= start:
        end += dt.timedelta(days=1)
    return start, end


def do_check_in(db: Session, emp: Employee, now: dt.datetime | None = None):
    now = now or dt.datetime.now()
    shift = shift_of(db, emp.id)
    day = now.date()
    if shift and is_overnight(shift) and now.time() < shift.end_time:
        day -= dt.timedelta(days=1)  # after midnight still belongs to yesterday's night shift
    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.date == day))
    if rec and rec.check_in:
        raise HTTPException(400, "You have already checked in today")
    status, flag, late = "present", "no_shift", 0
    if shift:
        start, _ = shift_window(shift, day)
        diff = int((now - start).total_seconds() // 60)
        if diff > settings.grace_minutes:
            status, flag, late = "late", "late", diff
        elif diff < -settings.early_window_minutes:
            flag = "early"
        else:
            flag = "on_time"
    if rec is None:
        rec = Attendance(employee_id=emp.id, date=day)
        db.add(rec)
    rec.check_in, rec.status, rec.checkin_flag, rec.late_minutes, rec.source = now, status, flag, late, "manual"
    if status == "late":
        msg = f"{emp.name} checked in {late} min after shift start."
        notify(db, emp.user_id, "Late check-in", f"You checked in {late} minutes late.", "late")
        mid = manager_user_id(db, emp)
        if mid:
            notify(db, mid, "Late attendance", msg, "late")
        notify_hr(db, "Late attendance", msg, "late")
    db.commit()
    return rec


def do_check_out(db: Session, emp: Employee, now: dt.datetime | None = None):
    now = now or dt.datetime.now()
    rec = db.scalar(select(Attendance).where(
        Attendance.employee_id == emp.id, Attendance.check_in.is_not(None),
        Attendance.check_out.is_(None)).order_by(Attendance.date.desc()))
    if not rec or (now - rec.check_in) > dt.timedelta(hours=20):
        raise HTTPException(400, "No active check-in found")
    shift = shift_of(db, emp.id)
    if shift:
        _, end = shift_window(shift, rec.date)
        early = int((end - now).total_seconds() // 60)
        rec.early_leave_minutes = early if early > settings.grace_minutes else 0
    rec.check_out = now
    hours = (now - rec.check_in).total_seconds() / 3600
    if hours < 4:
        rec.status = "half_day"            # worked less than 4 hours
    elif hours > 8.5:
        rec.overtime_hours = round(hours - 8, 2)  # overtime beyond 8 hours
    db.commit()
    return rec


def auto_mark(db: Session, now: dt.datetime | None = None) -> int:
    """Mark absent / on_leave for shifts that already ended without a check-in (today & yesterday)."""
    now = now or dt.datetime.now()
    marked = 0
    leave_cache = {}
    for emp in db.scalars(select(Employee).where(Employee.status == "active")):
        shift = shift_of(db, emp.id)
        if not shift:
            continue
        for day in (now.date() - dt.timedelta(days=1), now.date()):
            if day.weekday() >= 5 or day < emp.join_date:
                continue
            _, end = shift_window(shift, day)
            if now < end:
                continue
            if db.scalar(select(Attendance.id).where(Attendance.employee_id == emp.id, Attendance.date == day)):
                continue
            if day not in leave_cache:
                leave_cache[day] = on_leave_ids(db, day)
            on_leave = emp.id in leave_cache[day]
            db.add(Attendance(employee_id=emp.id, date=day, status="on_leave" if on_leave else "absent",
                              checkin_flag=None, source="auto"))
            if not on_leave:
                marked += 1
                notify(db, emp.user_id, "Marked absent",
                       f"No check-in was recorded for {day.isoformat()}. Contact HR if this is wrong.", "late")
    db.commit()
    return marked


def expiry_alerts(db: Session) -> int:
    limit = dt.date.today() + dt.timedelta(days=30)
    n = 0
    for doc in db.scalars(select(Document).where(Document.expiry_date.is_not(None),
                                                 Document.expiry_date <= limit,
                                                 Document.expiry_notified == False)):  # noqa: E712
        emp = doc.employee
        msg = f"{doc.file_name} ({emp.name}) expires on {doc.expiry_date.isoformat()}."
        notify(db, emp.user_id, "Document expiring", msg, "document")
        notify_hr(db, "Document expiring", msg, "document")
        doc.expiry_notified = True
        n += 1
    db.commit()
    return n


# ---------- leaves ----------
def init_balances(db: Session, employee_id: int, year: int | None = None):
    year = year or dt.date.today().year
    for p in db.scalars(select(LeavePolicy)):
        exists = db.scalar(select(LeaveBalance.id).where(
            LeaveBalance.employee_id == employee_id, LeaveBalance.leave_type == p.leave_type,
            LeaveBalance.year == year))
        if not exists:
            db.add(LeaveBalance(employee_id=employee_id, leave_type=p.leave_type, year=year,
                                total=p.days_per_year, used=0))


def dept_conflicts(db: Session, emp: Employee, start: dt.date, end: dt.date, exclude_id: int = 0):
    """Dates in [start, end] where the department already has too many approved leaves."""
    rows = db.execute(select(Leave.employee_id, Leave.start_date, Leave.end_date)
                      .join(Employee, Employee.id == Leave.employee_id)
                      .where(Employee.department == emp.department, Employee.id != emp.id,
                             Leave.status == "approved", Leave.start_date <= end,
                             Leave.end_date >= start, Leave.id != exclude_id)).all()
    bad, d = [], start
    while d <= end:
        if d.weekday() < 5:
            n = len({r.employee_id for r in rows if r.start_date <= d <= r.end_date})
            if n >= settings.leave_conflict_limit:
                bad.append(d)
        d += dt.timedelta(days=1)
    return bad


# ---------- onboarding ----------
DEFAULT_ONBOARDING = [("Submit ID and address proof", 3), ("Sign employment contract", 3),
                      ("Set up work email and tools", 5), ("Meet your manager for a welcome chat", 5),
                      ("Complete HR orientation", 7), ("Read the company policies", 10)]


def default_onboarding(db: Session, emp: Employee) -> int:
    from .models import Onboarding
    have = set(db.scalars(select(Onboarding.task_name).where(Onboarding.employee_id == emp.id)))
    base, n = max(emp.join_date, dt.date.today()), 0
    for name, off in DEFAULT_ONBOARDING:
        if name not in have:
            db.add(Onboarding(employee_id=emp.id, task_name=name, due_date=base + dt.timedelta(days=off)))
            n += 1
    return n


# ---------- aggregates ----------
def avg_ratings(db: Session) -> dict:
    rows = db.execute(select(Performance.employee_id, func.avg(Performance.rating))
                      .group_by(Performance.employee_id)).all()
    return {r[0]: round(float(r[1]), 2) for r in rows}
