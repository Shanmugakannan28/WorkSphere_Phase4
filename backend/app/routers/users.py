"""Admin user management: list, change role, activate/deactivate, reset password, delete."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import (Attendance, Document, Employee, EmployeeShift, Leave, LeaveBalance,
                      Notification, Onboarding, Payroll, Performance, Resignation, Task, Feedback,
                      Announcement, User)
from ..schemas import ResetPasswordIn, UserUpdate
from ..security import hash_password, require_roles

router = APIRouter(prefix="/api/users", tags=["User management"])
ADMIN = require_roles("admin")


@router.get("")
def list_users(db: Session = Depends(get_db), admin: User = Depends(ADMIN)):
    rows = db.execute(select(User, Employee).select_from(User)
                      .outerjoin(Employee, Employee.user_id == User.id).order_by(User.id)).all()
    return [{"id": u.id, "username": u.username, "email": u.email, "role": u.role, "is_active": u.is_active,
             "name": e.name if e else None, "department": e.department if e else None,
             "employee_id": e.id if e else None} for u, e in rows]


@router.put("/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(ADMIN)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot change your own role or status")
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
        emp = db.scalar(select(Employee).where(Employee.user_id == u.id))
        if emp:
            emp.status = "active" if body.is_active else "inactive"
    db.commit()
    return {"ok": True}


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, body: ResetPasswordIn, db: Session = Depends(get_db), admin: User = Depends(ADMIN)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(ADMIN)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")
    emp = db.scalar(select(Employee).where(Employee.user_id == u.id))
    if emp:
        for d in db.scalars(select(Document).where(Document.employee_id == emp.id)):
            (settings.storage_dir / d.stored_name).unlink(missing_ok=True)
        for model in (Document, Attendance, Leave, LeaveBalance, Payroll, Performance, EmployeeShift,
                      Onboarding, Resignation, Feedback):
            db.execute(delete(model).where(model.employee_id == emp.id))
        db.execute(delete(Task).where(Task.assigned_to == emp.id))
        db.execute(update(Employee).where(Employee.manager_id == emp.id).values(manager_id=None))
        db.execute(update(Leave).where(Leave.reviewed_by == u.id).values(reviewed_by=None))
        db.delete(emp)
    db.execute(update(Performance).where(Performance.reviewer_id == u.id).values(reviewer_id=admin.id))
    db.execute(update(Task).where(Task.assigned_by == u.id).values(assigned_by=admin.id))
    db.execute(update(Announcement).where(Announcement.created_by == u.id).values(created_by=admin.id))
    db.execute(delete(Notification).where(Notification.user_id == u.id))
    db.delete(u)
    db.commit()
    return {"ok": True}
