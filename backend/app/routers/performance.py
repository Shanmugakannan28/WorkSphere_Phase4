from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee, Performance, User
from ..schemas import PerformanceIn
from ..security import current_user, require_roles
from ..services import ensure_access, my_employee, notify, scope_ids

router = APIRouter(prefix="/api/performance", tags=["Performance"])


@router.post("", status_code=201)
def add_review(body: PerformanceIn, db: Session = Depends(get_db),
               user: User = Depends(require_roles("admin", "hr", "manager"))):
    emp = db.get(Employee, body.employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    ensure_access(db, user, emp.id)
    me = my_employee(db, user)
    if me and me.id == emp.id:
        raise HTTPException(403, "You cannot review yourself")
    p = Performance(employee_id=emp.id, reviewer_id=user.id, review_period=body.review_period,
                    rating=round(body.rating * 2) / 2, feedback=body.feedback)
    db.add(p)
    notify(db, emp.user_id, "New performance review",
           f"A review for {body.review_period} was added (rating {p.rating}/5).", "performance")
    db.commit()
    return {"id": p.id}


@router.get("")
def list_reviews(employee_id: Optional[int] = None, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    me = my_employee(db, user)
    stmt = select(Performance).order_by(Performance.created_at.desc())
    if employee_id:
        ensure_access(db, user, employee_id)
        stmt = stmt.where(Performance.employee_id == employee_id)
    else:
        ids = scope_ids(db, user)
        if ids is not None:
            stmt = stmt.where(Performance.employee_id.in_(ids))
    names = {e.user_id: e.name for e in db.scalars(select(Employee))}
    return [{"id": p.id, "employee_id": p.employee_id, "employee_name": p.employee.name,
             "review_period": p.review_period, "rating": p.rating, "feedback": p.feedback,
             "reviewer": names.get(p.reviewer_id, "Reviewer"), "created_at": p.created_at}
            for p in db.scalars(stmt.limit(500))]
