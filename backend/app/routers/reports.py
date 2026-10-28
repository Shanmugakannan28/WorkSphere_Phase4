"""CSV / PDF exports. Every dataset is role-scoped exactly like the matching API."""
import csv
import datetime as dt
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attendance, Employee, Feedback, Leave, Payroll, User
from ..pdfgen import table_pdf
from ..security import current_user
from ..services import my_employee, scope_ids

router = APIRouter(prefix="/api/reports", tags=["Reports"])
HR = ("admin", "hr")


def _t(v):
    return v.strftime("%H:%M") if v else ""


def employees(db, user, start, end):
    if user.role == "employee":
        raise HTTPException(403, "You do not have permission to export this report")
    stmt = select(Employee, User).select_from(Employee).join(User, User.id == Employee.user_id).order_by(Employee.name)
    ids = scope_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Employee.id.in_(ids))
    hr = user.role in HR
    head = ["ID", "Name", "Email", "Department", "Job title", "System role", "Status", "Joined"] + (["Monthly salary"] if hr else [])
    rows = [[e.id, e.name, e.email, e.department, e.designation, u.role, e.status, e.join_date] + ([e.salary] if hr else [])
            for e, u in db.execute(stmt)]
    return "Employee list", head, rows


def attendance(db, user, start, end):
    stmt = select(Attendance, Employee.name).select_from(Attendance).join(Employee, Employee.id == Attendance.employee_id) \
        .where(Attendance.date.between(start, end)).order_by(Attendance.date.desc(), Employee.name)
    ids = scope_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Attendance.employee_id.in_(ids))
    rows = [[a.date, n, a.status, _t(a.check_in), _t(a.check_out), a.late_minutes, a.early_leave_minutes, a.overtime_hours]
            for a, n in db.execute(stmt.limit(5000))]
    return "Attendance report", ["Date", "Employee", "Status", "Check-in", "Check-out", "Late (min)", "Early leave (min)", "Overtime (h)"], rows


def leaves(db, user, start, end):
    stmt = select(Leave).where(Leave.start_date <= end, Leave.end_date >= start).order_by(Leave.start_date.desc())
    ids = scope_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Leave.employee_id.in_(ids))
    rows = [[l.employee.name, l.employee.department, l.leave_type, l.start_date, l.end_date, l.days, l.status, l.reason]
            for l in db.scalars(stmt.limit(5000))]
    return "Leave report", ["Employee", "Department", "Type", "From", "To", "Days", "Status", "Reason"], rows


def payroll(db, user, start, end):
    stmt = select(Payroll).order_by(Payroll.month.desc())
    if user.role not in HR:
        me = my_employee(db, user)
        stmt = stmt.where(Payroll.employee_id == (me.id if me else 0))
    rows = [[p.month, p.employee.name, p.basic, p.allowances, p.bonus, p.deductions, p.net, p.status]
            for p in db.scalars(stmt.limit(5000))]
    return "Payroll report", ["Month", "Employee", "Basic", "Allowances", "Bonus/OT", "Deductions", "Net pay", "Status"], rows


def feedback(db, user, start, end):
    if user.role not in HR:
        raise HTTPException(403, "You do not have permission to export this report")
    rows = [[f.created_at.date(), "Anonymous" if f.anonymous else f.employee.name, f.rating, f.message]
            for f in db.scalars(select(Feedback).where(Feedback.created_at >= dt.datetime.combine(start, dt.time.min),
                                                       Feedback.created_at <= dt.datetime.combine(end, dt.time.max))
                                .order_by(Feedback.created_at.desc()).limit(5000))]
    return "Employee feedback", ["Date", "Employee", "Rating", "Message"], rows


DATASETS = {"employees": employees, "attendance": attendance, "leaves": leaves, "payroll": payroll, "feedback": feedback}


def _safe(v):
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/{kind}")
def export(kind: str, format: str = Query("csv", pattern="^(csv|pdf)$"), start: Optional[dt.date] = None,
           end: Optional[dt.date] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind not in DATASETS:
        raise HTTPException(404, "Unknown report")
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=29)
    if start > end or (end - start).days > 366:
        raise HTTPException(400, "Invalid date range (max 366 days)")
    title, head, rows = DATASETS[kind](db, user, start, end)
    name = f"{kind}-{dt.date.today()}"
    if format == "pdf":
        sub = f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} by {user.username}" + (f" | {start} to {end}" if kind in ("attendance", "leaves", "feedback") else "")
        return Response(table_pdf(title, head, rows, sub), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    for r in rows:
        w.writerow([_safe(c) for c in r])
    return Response(("\ufeff" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
