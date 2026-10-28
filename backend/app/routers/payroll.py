import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Attendance, Employee, Payroll, User
from ..schemas import PayrollRunIn
from ..security import current_user, require_roles
from ..services import my_employee, notify

router = APIRouter(prefix="/api/payroll", tags=["Payroll"])
WORKING_DAYS = 22


@router.post("/process")
def process(body: PayrollRunIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    y, m = map(int, body.month.split("-"))
    first = dt.date(y, m, 1)
    last = (dt.date(y + (m == 12), m % 12 + 1, 1)) - dt.timedelta(days=1)
    count = 0
    for e in db.scalars(select(Employee).where(Employee.status == "active")):
        if e.join_date > last or db.scalar(select(Payroll.id).where(Payroll.employee_id == e.id, Payroll.month == body.month)):
            continue
        absent = db.scalar(select(func.count(Attendance.id)).where(
            Attendance.employee_id == e.id, Attendance.status == "absent",
            Attendance.date.between(first, last))) or 0
        half = db.scalar(select(func.count(Attendance.id)).where(
            Attendance.employee_id == e.id, Attendance.status == "half_day",
            Attendance.date.between(first, last))) or 0
        ot = db.scalar(select(func.coalesce(func.sum(Attendance.overtime_hours), 0)).where(
            Attendance.employee_id == e.id, Attendance.date.between(first, last))) or 0
        per_day = e.salary / WORKING_DAYS
        basic = round(e.salary * 0.6, 2)                 # 60% basic
        allowances = round(e.salary - basic, 2)          # 40% HRA + other allowances
        ded = round(absent * per_day + half * per_day / 2, 2)
        bonus = round(ot * per_day / 8 * 1.5, 2)         # overtime at 1.5x hourly rate
        db.add(Payroll(employee_id=e.id, month=body.month, basic=basic, allowances=allowances,
                       deductions=ded, bonus=bonus, net=round(basic + allowances + bonus - ded, 2),
                       status="processed"))
        notify(db, e.user_id, "Payroll processed", f"Your salary for {body.month} has been processed.", "payroll")
        count += 1
    db.commit()
    return {"processed": count}


@router.get("")
def list_payroll(month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Payroll).order_by(Payroll.month.desc())
    if user.role not in ("admin", "hr"):
        me = my_employee(db, user)
        stmt = stmt.where(Payroll.employee_id == (me.id if me else 0))
    if month:
        stmt = stmt.where(Payroll.month == month)
    return [{"id": p.id, "employee_id": p.employee_id, "employee_name": p.employee.name,
             "department": p.employee.department, "month": p.month, "basic": p.basic, "allowances": p.allowances,
             "deductions": p.deductions, "bonus": p.bonus, "net": p.net, "status": p.status,
             "processed_at": p.processed_at} for p in db.scalars(stmt.limit(500))]
