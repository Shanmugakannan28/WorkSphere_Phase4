import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attendance, Employee, EmployeeShift, Shift, User
from ..schemas import EmployeeIn, EmployeeUpdate
from ..security import current_user, hash_password, require_roles
from ..config import settings
from ..services import (avg_ratings, default_onboarding, init_balances, my_employee, notify, on_leave_ids, scope_ids,
                        shift_of, unique_username)

router = APIRouter(prefix="/api/employees", tags=["Employees"])
STAFF = ("admin", "hr", "manager")


@router.get("/meta")
def meta(db: Session = Depends(get_db), user: User = Depends(current_user)):
    depts = sorted(set(db.scalars(select(Employee.department))))
    desig = sorted(set(db.scalars(select(Employee.designation))))
    mgrs = db.execute(select(Employee.id, Employee.name).join(User, User.id == Employee.user_id)
                      .where(User.role.in_(("admin", "hr", "manager"))).order_by(Employee.name)).all()
    return {"departments": depts, "designations": desig,
            "managers": [{"id": m.id, "name": m.name} for m in mgrs]}


@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = my_employee(db, user)
    if not e:
        raise HTTPException(404, "No employee profile")
    mgr = db.get(Employee, e.manager_id) if e.manager_id else None
    sh = shift_of(db, e.id)
    return {"id": e.id, "name": e.name, "username": user.username, "email": e.email, "role": user.role,
            "department": e.department, "designation": e.designation, "status": e.status,
            "join_date": e.join_date, "phone": e.phone, "address": e.address, "salary": e.salary, "manager": mgr.name if mgr else None,
            "shift": f"{sh.name} ({sh.start_time:%H:%M}-{sh.end_time:%H:%M})" if sh else None}


@router.get("")
def list_employees(q: Optional[str] = None, department: Optional[str] = None, role: Optional[str] = None,
                   status: Optional[str] = Query(None, pattern="^(active|inactive|on_leave)$"),
                   attendance: Optional[str] = Query(None, pattern="^(present|late|absent|on_leave|not_marked)$"),
                   min_rating: Optional[float] = Query(None, ge=0, le=5),
                   max_rating: Optional[float] = Query(None, ge=0, le=5),
                   db: Session = Depends(get_db), user: User = Depends(require_roles(*STAFF))):
    stmt = select(Employee, User).select_from(Employee).join(User, User.id == Employee.user_id)
    ids = scope_ids(db, user)
    if ids is not None:
        stmt = stmt.where(Employee.id.in_(ids))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Employee.name.ilike(like), Employee.email.ilike(like),
                              Employee.department.ilike(like), Employee.designation.ilike(like)))
    if department:
        stmt = stmt.where(Employee.department == department)
    if role:
        like = f"%{role.strip()}%"
        stmt = stmt.where(or_(Employee.designation.ilike(like), User.role == role.strip().lower()))
    if status in ("active", "inactive"):
        stmt = stmt.where(Employee.status == status)
    rows = db.execute(stmt.order_by(Employee.name)).all()

    today = dt.date.today()
    leave_set = on_leave_ids(db, today)
    att_map = {a.employee_id: a.status for a in db.scalars(select(Attendance).where(Attendance.date == today))}
    ratings = avg_ratings(db)
    shifts = {es.employee_id: s.name for es, s in db.execute(
        select(EmployeeShift, Shift).select_from(EmployeeShift).join(Shift, Shift.id == EmployeeShift.shift_id)).all()}
    see_salary = user.role in ("admin", "hr")
    out = []
    for e, u in rows:
        today_status = att_map.get(e.id) or ("on_leave" if e.id in leave_set else "not_marked")
        rating = ratings.get(e.id)
        if status == "on_leave" and e.id not in leave_set:
            continue
        if attendance and today_status != attendance:
            continue
        if min_rating is not None and (rating is None or rating < min_rating):
            continue
        if max_rating is not None and (rating is None or rating > max_rating):
            continue
        out.append({"id": e.id, "name": e.name, "email": e.email, "department": e.department,
                    "designation": e.designation, "role": u.role, "status": e.status,
                    "on_leave_today": e.id in leave_set, "today_attendance": today_status,
                    "avg_rating": rating, "shift": shifts.get(e.id), "manager_id": e.manager_id,
                    "join_date": e.join_date, "salary": e.salary if see_salary else None})
    return out


@router.post("", status_code=201)
def create_employee(body: EmployeeIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "hr"))):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    if body.role == "admin" and user.role != "admin":
        raise HTTPException(403, "Only an admin can create admins")
    if body.manager_id and not db.get(Employee, body.manager_id):
        raise HTTPException(400, "Manager not found")
    if body.shift_id and not db.get(Shift, body.shift_id):
        raise HTTPException(400, "Shift not found")
    if body.username and db.scalar(select(User.id).where(User.username == body.username.lower())):
        raise HTTPException(409, "This username is taken")
    uname = body.username.lower() if body.username else unique_username(db, email.split("@")[0])
    u = User(username=uname, email=email, password_hash=hash_password(body.password or settings.default_password), role=body.role)
    db.add(u)
    db.flush()
    e = Employee(user_id=u.id, name=body.name, email=email, department=body.department,
                 designation=body.designation, manager_id=body.manager_id, salary=body.salary,
                 join_date=body.join_date or dt.date.today())
    db.add(e)
    db.flush()
    init_balances(db, e.id)
    default_onboarding(db, e)
    if body.shift_id:
        db.add(EmployeeShift(employee_id=e.id, shift_id=body.shift_id))
    notify(db, u.id, "Welcome to WorkSphere", "Your account is ready. Please change your password.", "info")
    db.commit()
    return {"id": e.id}


@router.put("/{employee_id}")
def update_employee(employee_id: int, body: EmployeeUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "hr"))):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(404, "Employee not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("role") == "admin" and user.role != "admin":
        raise HTTPException(403, "Only an admin can grant the admin role")
    if e.user.role == "admin" and user.role != "admin":
        raise HTTPException(403, "Only an admin can edit an admin")
    if data.get("status") == "inactive" and e.user_id == user.id:
        raise HTTPException(400, "You cannot deactivate your own account")
    if data.get("manager_id") == e.id:
        raise HTTPException(400, "An employee cannot manage themselves")
    if "role" in data and data["role"]:
        e.user.role = data.pop("role")
    if data.get("status"):
        e.user.is_active = data["status"] == "active"
    for k, v in data.items():
        setattr(e, k, v)
    db.commit()
    return {"ok": True}
