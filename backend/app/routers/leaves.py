import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Employee, Leave, LeaveBalance, LeavePolicy, User
from ..schemas import LeaveIn, ReviewIn
from ..security import current_user, require_roles
from ..services import (dept_conflicts, ensure_access, init_balances, manager_user_id, my_employee,
                        notify, notify_hr, scope_ids, workdays)

router = APIRouter(prefix="/api/leaves", tags=["Leaves"])


def _me(db, user):
    emp = my_employee(db, user)
    if not emp:
        raise HTTPException(400, "No employee profile is linked to this account")
    return emp


def _ser(l: Leave, reviewer_ok=False):
    return {"id": l.id, "employee_id": l.employee_id, "employee_name": l.employee.name,
            "department": l.employee.department, "leave_type": l.leave_type, "start_date": l.start_date,
            "end_date": l.end_date, "days": l.days, "reason": l.reason, "status": l.status,
            "created_at": l.created_at, "can_review": reviewer_ok and l.status == "pending"}


@router.get("/policies")
def policies(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"policies": [{"leave_type": p.leave_type, "days_per_year": p.days_per_year}
                         for p in db.scalars(select(LeavePolicy))],
            "conflict_limit": settings.leave_conflict_limit}


@router.get("/balance")
def balance(employee_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    emp_id = employee_id or _me(db, user).id
    ensure_access(db, user, emp_id)
    year = dt.date.today().year
    init_balances(db, emp_id, year)
    db.commit()
    rows = db.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == emp_id, LeaveBalance.year == year))
    return [{"leave_type": b.leave_type, "total": b.total, "used": b.used,
             "remaining": None if b.total == 0 else b.total - b.used} for b in rows]


@router.get("/conflicts")
def conflicts(start: dt.date, end: dt.date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if end < start or (end - start).days > 90:
        raise HTTPException(400, "Invalid date range")
    emp = _me(db, user)
    return {"dates": dept_conflicts(db, emp, start, end), "limit": settings.leave_conflict_limit}


@router.post("", status_code=201)
def apply(body: LeaveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    emp = _me(db, user)
    policy = db.scalar(select(LeavePolicy).where(LeavePolicy.leave_type == body.leave_type))
    if not policy:
        raise HTTPException(400, "Unknown leave type")
    days = workdays(body.start_date, body.end_date)
    if days < 1:
        raise HTTPException(400, "The selected dates contain no working days")
    overlap = db.scalar(select(Leave.id).where(
        Leave.employee_id == emp.id, Leave.status.in_(("pending", "approved")),
        Leave.start_date <= body.end_date, Leave.end_date >= body.start_date))
    if overlap:
        raise HTTPException(409, "You already have a leave request overlapping these dates")
    if policy.days_per_year > 0:
        init_balances(db, emp.id, body.start_date.year)
        bal = db.scalar(select(LeaveBalance).where(
            LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type == body.leave_type,
            LeaveBalance.year == body.start_date.year))
        if not bal or bal.total - bal.used < days:
            raise HTTPException(400, f"Not enough {body.leave_type} leave balance for {days} day(s)")
    bad = dept_conflicts(db, emp, body.start_date, body.end_date)
    if bad:
        raise HTTPException(409, f"Too many people in {emp.department} are already on leave on "
                                 f"{', '.join(d.isoformat() for d in bad[:3])}. Choose different dates.")
    leave = Leave(employee_id=emp.id, leave_type=body.leave_type, start_date=body.start_date,
                  end_date=body.end_date, days=days, reason=body.reason)
    db.add(leave)
    msg = f"{emp.name} requested {days} day(s) of {body.leave_type} leave from {body.start_date}."
    mid = manager_user_id(db, emp)
    if mid:
        notify(db, mid, "Leave request", msg, "leave")
    notify_hr(db, "Leave request", msg, "leave")
    db.commit()
    return {"id": leave.id, "days": days}


@router.get("")
def list_leaves(status: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = scope_ids(db, user)
    me = my_employee(db, user)
    stmt = select(Leave).order_by(Leave.created_at.desc()).limit(500)
    if ids is not None:
        stmt = stmt.where(Leave.employee_id.in_(ids))
    if status:
        stmt = stmt.where(Leave.status == status)
    can = user.role in ("admin", "hr", "manager")
    return [_ser(l, can and me is not None and l.employee_id != me.id) for l in db.scalars(stmt)]


@router.put("/{leave_id}/review")
def review(leave_id: int, body: ReviewIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles("admin", "hr", "manager"))):
    leave = db.get(Leave, leave_id)
    if not leave:
        raise HTTPException(404, "Leave request not found")
    ensure_access(db, user, leave.employee_id)
    me = my_employee(db, user)
    if me and me.id == leave.employee_id:
        raise HTTPException(403, "You cannot review your own leave request")
    if leave.status != "pending":
        raise HTTPException(400, f"This request is already {leave.status}")
    if body.status == "approved":
        if dept_conflicts(db, leave.employee, leave.start_date, leave.end_date, exclude_id=leave.id):
            raise HTTPException(409, "Approving this would leave the department understaffed on some dates")
        year = leave.start_date.year
        init_balances(db, leave.employee_id, year)
        bal = db.scalar(select(LeaveBalance).where(
            LeaveBalance.employee_id == leave.employee_id, LeaveBalance.leave_type == leave.leave_type,
            LeaveBalance.year == year))
        if bal:
            if bal.total > 0 and bal.total - bal.used < leave.days:
                raise HTTPException(400, "Employee no longer has enough balance")
            bal.used += leave.days
    leave.status, leave.reviewed_by = body.status, user.id
    notify(db, leave.employee.user_id, f"Leave {body.status}",
           f"Your {leave.leave_type} leave ({leave.start_date} to {leave.end_date}) was {body.status}.", "leave")
    db.commit()
    return {"ok": True}


@router.delete("/{leave_id}")
def cancel(leave_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    leave = db.get(Leave, leave_id)
    me = my_employee(db, user)
    if not leave or not me or leave.employee_id != me.id:
        raise HTTPException(404, "Leave request not found")
    if leave.status != "pending":
        raise HTTPException(400, "Only pending requests can be cancelled")
    leave.status = "cancelled"
    db.commit()
    return {"ok": True}


def _dept_filter(db, user, stmt, department):
    if user.role in ("admin", "hr"):
        return stmt.where(Employee.department == department) if department else stmt
    me = my_employee(db, user)
    return stmt.where(Employee.department == (me.department if me else ""))


@router.get("/calendar")
def calendar(start: dt.date, end: dt.date, department: Optional[str] = None,
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    if end < start or (end - start).days > 100:
        raise HTTPException(400, "Invalid date range")
    me = my_employee(db, user)
    stmt = select(Leave).join(Employee, Employee.id == Leave.employee_id).where(
        Leave.status.in_(("approved", "pending")), Leave.start_date <= end, Leave.end_date >= start)
    stmt = _dept_filter(db, user, stmt, department)
    out = []
    for l in db.scalars(stmt.order_by(Leave.start_date)):
        # colleagues only see approved leave; staff see pending too; everyone sees their own
        if l.status == "pending" and user.role == "employee" and (not me or l.employee_id != me.id):
            continue
        out.append({"id": l.id, "employee_id": l.employee_id, "name": l.employee.name,
                    "department": l.employee.department, "leave_type": l.leave_type,
                    "start_date": l.start_date, "end_date": l.end_date, "status": l.status})
    return out


@router.get("/availability")
def availability(day: dt.date, department: Optional[str] = None,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    estmt = _dept_filter(db, user, select(Employee).where(Employee.status == "active"), department)
    emps = list(db.scalars(estmt))
    on_leave = {l.employee_id: l.leave_type for l in db.scalars(select(Leave).where(
        Leave.status == "approved", Leave.start_date <= day, Leave.end_date >= day))}
    depts = {}
    for e in emps:
        d = depts.setdefault(e.department, {"department": e.department, "total": 0, "on_leave": []})
        d["total"] += 1
        if e.id in on_leave:
            d["on_leave"].append({"name": e.name, "leave_type": on_leave[e.id]})
    res = []
    for d in sorted(depts.values(), key=lambda x: x["department"]):
        d["available"] = d["total"] - len(d["on_leave"])
        res.append(d)
    return {"day": day, "departments": res, "conflict_limit": settings.leave_conflict_limit}
