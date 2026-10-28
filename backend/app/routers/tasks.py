import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee, Task, User
from ..schemas import StatusIn, TaskIn, TaskUpdate
from ..security import current_user, require_roles
from ..services import ensure_access, my_employee, notify, scope_ids

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


def _ser(t: Task, names: dict, uid: int, role: str):
    overdue = t.status == "pending" and t.due_date is not None and t.due_date < dt.date.today()
    return {"id": t.id, "assigned_to": t.assigned_to, "assignee_name": t.employee.name, "title": t.title,
            "description": t.description, "due_date": t.due_date, "status": t.status, "overdue": overdue,
            "assigned_by": names.get(t.assigned_by, "HR"), "created_at": t.created_at, "completed_at": t.completed_at,
            "can_manage": role in ("admin", "hr") or t.assigned_by == uid}


def _can_manage(t: Task, user: User):
    return user.role in ("admin", "hr") or t.assigned_by == user.id


@router.get("")
def list_tasks(status: Optional[str] = Query(None, pattern="^(pending|completed)$"), mine: bool = False,
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Task).order_by(Task.status.desc(), Task.due_date)
    if mine:
        me = my_employee(db, user)
        stmt = stmt.where(Task.assigned_to == (me.id if me else 0))
    else:
        ids = scope_ids(db, user)
        if ids is not None:
            stmt = stmt.where(Task.assigned_to.in_(ids))
    if status:
        stmt = stmt.where(Task.status == status)
    names = {e.user_id: e.name for e in db.scalars(select(Employee))}
    return [_ser(t, names, user.id, user.role) for t in db.scalars(stmt.limit(500))]


@router.post("", status_code=201)
def assign(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr", "manager"))):
    emp = db.get(Employee, body.assigned_to)
    if not emp or emp.status != "active":
        raise HTTPException(404, "Active employee not found")
    ensure_access(db, user, emp.id)
    t = Task(assigned_to=emp.id, assigned_by=user.id, title=body.title, description=body.description, due_date=body.due_date)
    db.add(t)
    notify(db, emp.user_id, "New task assigned", body.title + (f" (due {body.due_date})" if body.due_date else ""), "task")
    db.commit()
    return {"id": t.id}


@router.put("/{task_id}/status")
def set_status(task_id: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    me = my_employee(db, user)
    if not ((me and me.id == t.assigned_to) or _can_manage(t, user)):
        raise HTTPException(403, "You cannot update this task")
    t.status = body.status
    t.completed_at = dt.datetime.now() if body.status == "completed" else None
    if body.status == "completed" and t.assigned_by != user.id:
        notify(db, t.assigned_by, "Task completed", f"{t.employee.name} completed: {t.title}", "task")
    db.commit()
    return {"ok": True}


@router.put("/{task_id}")
def edit(task_id: int, body: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Task, task_id)
    if not t or not _can_manage(t, user):
        raise HTTPException(404, "Task not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/{task_id}")
def delete(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Task, task_id)
    if not t or not _can_manage(t, user):
        raise HTTPException(404, "Task not found")
    db.delete(t)
    db.commit()
    return {"ok": True}
