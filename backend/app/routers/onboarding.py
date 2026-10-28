import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee, Onboarding, User
from ..schemas import OnboardingIn, StatusIn
from ..security import current_user, require_roles
from ..services import default_onboarding, ensure_access, my_employee, notify, notify_hr, scope_ids

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


def _ser(t: Onboarding):
    overdue = t.status == "pending" and t.due_date is not None and t.due_date < dt.date.today()
    return {"id": t.id, "employee_id": t.employee_id, "employee_name": t.employee.name, "task_name": t.task_name,
            "status": t.status, "due_date": t.due_date, "completed_at": t.completed_at, "overdue": overdue}


@router.get("")
def list_tasks(employee_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Onboarding).order_by(Onboarding.status.desc(), Onboarding.due_date)
    if employee_id:
        ensure_access(db, user, employee_id)
        stmt = stmt.where(Onboarding.employee_id == employee_id)
    else:
        ids = scope_ids(db, user)
        if ids is not None:
            stmt = stmt.where(Onboarding.employee_id.in_(ids))
    return [_ser(t) for t in db.scalars(stmt.limit(1000))]


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr", "manager"))):
    ids = scope_ids(db, user)
    stmt = select(Onboarding)
    if ids is not None:
        stmt = stmt.where(Onboarding.employee_id.in_(ids))
    agg = {}
    for t in db.scalars(stmt):
        a = agg.setdefault(t.employee_id, {"employee_id": t.employee_id, "name": t.employee.name,
                                           "department": t.employee.department, "total": 0, "done": 0, "overdue": 0})
        a["total"] += 1
        a["done"] += t.status == "completed"
        a["overdue"] += t.status == "pending" and t.due_date is not None and t.due_date < dt.date.today()
    out = list(agg.values())
    for a in out:
        a["percent"] = round(100 * a["done"] / a["total"])
    return sorted(out, key=lambda x: (x["percent"], x["name"]))


@router.post("", status_code=201)
def add_task(body: OnboardingIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("admin", "hr", "manager"))):
    emp = db.get(Employee, body.employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    ensure_access(db, user, emp.id)
    t = Onboarding(employee_id=emp.id, task_name=body.task_name, due_date=body.due_date)
    db.add(t)
    notify(db, emp.user_id, "New onboarding task", body.task_name, "onboarding")
    db.commit()
    return {"id": t.id}


@router.post("/apply-default/{employee_id}")
def apply_default(employee_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    emp = db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    n = default_onboarding(db, emp)
    if n:
        notify(db, emp.user_id, "Onboarding checklist assigned", f"{n} onboarding tasks were added for you.", "onboarding")
    db.commit()
    return {"added": n}


@router.put("/{task_id}/status")
def set_status(task_id: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Onboarding, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    me = my_employee(db, user)
    is_owner = bool(me and me.id == t.employee_id)
    if not is_owner:
        if user.role not in ("admin", "hr", "manager"):
            raise HTTPException(403, "You can only update your own checklist")
        ensure_access(db, user, t.employee_id)
    t.status = body.status
    t.completed_at = dt.datetime.now() if body.status == "completed" else None
    db.flush()
    remaining = db.scalar(select(Onboarding.id).where(Onboarding.employee_id == t.employee_id, Onboarding.status == "pending"))
    if body.status == "completed" and remaining is None:
        notify_hr(db, "Onboarding complete", f"{t.employee.name} finished every onboarding task.", "onboarding")
    db.commit()
    return {"ok": True}


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr", "manager"))):
    t = db.get(Onboarding, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    ensure_access(db, user, t.employee_id)
    db.delete(t)
    db.commit()
    return {"ok": True}
