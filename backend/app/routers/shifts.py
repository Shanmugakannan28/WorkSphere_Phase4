from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee, EmployeeShift, Shift, User
from ..schemas import AssignIn, ShiftIn
from ..security import current_user, require_roles
from ..services import ensure_access, notify, scope_ids

router = APIRouter(prefix="/api/shifts", tags=["Shifts"])


@router.get("")
def list_shifts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": s.id, "name": s.name, "start_time": s.start_time, "end_time": s.end_time}
            for s in db.scalars(select(Shift).order_by(Shift.start_time))]


@router.post("", status_code=201)
def create_shift(body: ShiftIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    if db.scalar(select(Shift.id).where(Shift.name == body.name)):
        raise HTTPException(409, "A shift with this name already exists")
    s = Shift(name=body.name, start_time=body.start_time, end_time=body.end_time)
    db.add(s)
    db.commit()
    return {"id": s.id}


@router.put("/{shift_id}")
def update_shift(shift_id: int, body: ShiftIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("admin", "hr"))):
    s = db.get(Shift, shift_id)
    if not s:
        raise HTTPException(404, "Shift not found")
    s.name, s.start_time, s.end_time = body.name, body.start_time, body.end_time
    db.commit()
    return {"ok": True}


@router.get("/assignments")
def assignments(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = scope_ids(db, user)
    stmt = select(Employee, EmployeeShift, Shift).select_from(Employee).outerjoin(EmployeeShift, EmployeeShift.employee_id == Employee.id) \
        .outerjoin(Shift, Shift.id == EmployeeShift.shift_id).where(Employee.status == "active")
    if ids is not None:
        stmt = stmt.where(Employee.id.in_(ids))
    return [{"employee_id": e.id, "name": e.name, "department": e.department,
             "shift_id": s.id if s else None, "shift_name": s.name if s else None,
             "start_time": s.start_time if s else None, "end_time": s.end_time if s else None}
            for e, es, s in db.execute(stmt.order_by(Employee.name)).all()]


@router.post("/assign")
def assign(body: AssignIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles("admin", "hr", "manager"))):
    emp, shift = db.get(Employee, body.employee_id), db.get(Shift, body.shift_id)
    if not emp or not shift:
        raise HTTPException(404, "Employee or shift not found")
    ensure_access(db, user, emp.id)
    es = db.scalar(select(EmployeeShift).where(EmployeeShift.employee_id == emp.id))
    if es:
        es.shift_id = shift.id
    else:
        db.add(EmployeeShift(employee_id=emp.id, shift_id=shift.id))
    notify(db, emp.user_id, "Shift updated",
           f"You are now on the {shift.name} shift ({shift.start_time:%H:%M}-{shift.end_time:%H:%M}).", "info")
    db.commit()
    return {"ok": True}


@router.delete("/assign/{employee_id}")
def unassign(employee_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_roles("admin", "hr", "manager"))):
    ensure_access(db, user, employee_id)
    es = db.scalar(select(EmployeeShift).where(EmployeeShift.employee_id == employee_id))
    if es:
        db.delete(es)
        db.commit()
    return {"ok": True}
