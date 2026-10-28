import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Resignation, User
from ..schemas import ExitStageIn, ReviewIn, ResignationIn
from ..security import current_user, require_roles
from ..services import manager_user_id, my_employee, notify, notify_hr, scope_ids

router = APIRouter(prefix="/api/resignations", tags=["Exit management"])
STAGES = ["submitted", "notice_period", "handover", "clearance", "settlement", "completed"]


def _me(db, user):
    emp = my_employee(db, user)
    if not emp:
        raise HTTPException(400, "No employee profile is linked to this account")
    return emp


def _ser(r: Resignation):
    lwd = r.last_working_day or (r.created_at.date() + dt.timedelta(days=r.notice_period))
    return {"id": r.id, "employee_id": r.employee_id, "employee_name": r.employee.name,
            "department": r.employee.department, "reason": r.reason, "notice_period": r.notice_period,
            "status": r.status, "exit_stage": r.exit_stage, "last_working_day": lwd, "created_at": r.created_at}


@router.post("", status_code=201)
def submit(body: ResignationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    emp = _me(db, user)
    active = db.scalar(select(Resignation.id).where(
        Resignation.employee_id == emp.id, Resignation.status.in_(("pending", "approved")),
        Resignation.exit_stage != "completed"))
    if active:
        raise HTTPException(409, "You already have an active resignation")
    r = Resignation(employee_id=emp.id, reason=body.reason, notice_period=body.notice_period)
    db.add(r)
    msg = f"{emp.name} submitted a resignation with a {body.notice_period}-day notice period."
    notify_hr(db, "Resignation submitted", msg, "exit")
    mid = manager_user_id(db, emp)
    if mid:
        notify(db, mid, "Resignation submitted", msg, "exit")
    db.commit()
    return {"id": r.id}


@router.get("")
def list_resignations(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Resignation).order_by(Resignation.created_at.desc())
    ids = scope_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Resignation.employee_id.in_(ids))
    return [_ser(r) for r in db.scalars(stmt.limit(300))]


@router.put("/{rid}/review")
def review(rid: int, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    r = db.get(Resignation, rid)
    if not r:
        raise HTTPException(404, "Resignation not found")
    me = my_employee(db, user)
    if me and me.id == r.employee_id:
        raise HTTPException(403, "You cannot review your own resignation")
    if r.status != "pending":
        raise HTTPException(400, f"This resignation is already {r.status}")
    r.status, r.reviewed_by = body.status, user.id
    if body.status == "approved":
        r.exit_stage = "notice_period"
        r.last_working_day = r.created_at.date() + dt.timedelta(days=r.notice_period)
    notify(db, r.employee.user_id, f"Resignation {body.status}",
           "Your last working day is " + str(r.last_working_day) if body.status == "approved"
           else "Your resignation was not accepted. Please contact HR.", "exit")
    db.commit()
    return {"ok": True}


@router.put("/{rid}/stage")
def set_stage(rid: int, body: ExitStageIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    r = db.get(Resignation, rid)
    if not r:
        raise HTTPException(404, "Resignation not found")
    if r.status != "approved":
        raise HTTPException(400, "Approve the resignation before tracking the exit")
    if r.employee.user_id == user.id:
        raise HTTPException(403, "You cannot manage your own exit")
    r.exit_stage = body.stage
    if body.stage == "completed":
        r.employee.status = "inactive"
        r.employee.user.is_active = False
    else:
        notify(db, r.employee.user_id, "Exit process update", f"Your exit is now at: {body.stage.replace('_', ' ')}.", "exit")
    db.commit()
    return {"ok": True}


@router.delete("/{rid}")
def withdraw(rid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    r = db.get(Resignation, rid)
    me = my_employee(db, user)
    if not r or not me or r.employee_id != me.id:
        raise HTTPException(404, "Resignation not found")
    if r.status != "pending":
        raise HTTPException(400, "Only pending resignations can be withdrawn")
    r.status = "withdrawn"
    db.commit()
    return {"ok": True}
