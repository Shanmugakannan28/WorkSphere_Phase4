import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Attendance, Employee, User
from ..security import current_user, require_roles
from ..services import (auto_mark, do_check_in, do_check_out, ensure_access, is_overnight,
                        my_employee, scope_ids, shift_of)

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


def _ser(a: Attendance, name=None):
    hours = round((a.check_out - a.check_in).total_seconds() / 3600, 2) if a.check_in and a.check_out else None
    return {"id": a.id, "employee_id": a.employee_id, "employee_name": name, "date": a.date,
            "check_in": a.check_in, "check_out": a.check_out, "status": a.status,
            "checkin_flag": a.checkin_flag, "late_minutes": a.late_minutes,
            "early_leave_minutes": a.early_leave_minutes, "overtime_hours": a.overtime_hours, "hours": hours, "source": a.source}


def _me(db, user):
    emp = my_employee(db, user)
    if not emp:
        raise HTTPException(400, "No employee profile is linked to this account")
    return emp


@router.get("/today")
def today(db: Session = Depends(get_db), user: User = Depends(current_user)):
    emp = _me(db, user)
    shift = shift_of(db, emp.id)
    now = dt.datetime.now()
    day = now.date()
    if shift and is_overnight(shift) and now.time() < shift.end_time:
        day -= dt.timedelta(days=1)
    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.date == day))
    return {"employee": {"id": emp.id, "name": emp.name},
            "shift": {"name": shift.name, "start_time": shift.start_time, "end_time": shift.end_time} if shift else None,
            "record": _ser(rec, emp.name) if rec else None,
            "grace_minutes": settings.grace_minutes}


@router.post("/check-in")
def check_in(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _ser(do_check_in(db, _me(db, user)))


@router.post("/check-out")
def check_out(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _ser(do_check_out(db, _me(db, user)))


@router.get("")
def list_attendance(employee_id: Optional[int] = None, start: Optional[dt.date] = None,
                    end: Optional[dt.date] = None, status: Optional[str] = Query(None, pattern="^(present|late|half_day|absent|on_leave)$"),
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=29)
    if (end - start).days > 366:
        raise HTTPException(400, "Date range too large")
    stmt = select(Attendance, Employee.name).select_from(Attendance).join(Employee, Employee.id == Attendance.employee_id) \
        .where(Attendance.date.between(start, end))
    if employee_id:
        ensure_access(db, user, employee_id)
        stmt = stmt.where(Attendance.employee_id == employee_id)
    else:
        ids = scope_ids(db, user)
        if ids is not None:
            stmt = stmt.where(Attendance.employee_id.in_(ids))
    if status:
        stmt = stmt.where(Attendance.status == status)
    rows = db.execute(stmt.order_by(Attendance.date.desc(), Employee.name).limit(1000)).all()
    return [_ser(a, n) for a, n in rows]


@router.post("/auto-mark")
def run_auto_mark(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    return {"marked_absent": auto_mark(db)}
