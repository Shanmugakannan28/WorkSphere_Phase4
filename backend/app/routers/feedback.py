from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Feedback, User
from ..schemas import FeedbackIn
from ..security import current_user
from ..services import my_employee, notify_hr
from fastapi import HTTPException

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


@router.post("", status_code=201)
def submit(body: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    me = my_employee(db, user)
    if not me:
        raise HTTPException(400, "No employee profile is linked to this account")
    f = Feedback(employee_id=me.id, message=body.message, rating=body.rating, anonymous=body.anonymous)
    db.add(f)
    if body.rating <= 2:
        notify_hr(db, "Low feedback rating", f"A {body.rating}/5 feedback was submitted.", "info")
    db.commit()
    return {"id": f.id}


@router.get("")
def list_feedback(db: Session = Depends(get_db), user: User = Depends(current_user)):
    hr = user.role in ("admin", "hr")
    stmt = select(Feedback).order_by(Feedback.created_at.desc())
    if not hr:
        me = my_employee(db, user)
        stmt = stmt.where(Feedback.employee_id == (me.id if me else 0))
    rows = list(db.scalars(stmt.limit(500)))
    items = [{"id": f.id, "message": f.message, "rating": f.rating, "created_at": f.created_at,
              "anonymous": f.anonymous,
              "employee_name": ("Anonymous" if f.anonymous and hr else f.employee.name),
              "department": (None if f.anonymous and hr else f.employee.department)} for f in rows]
    summary = None
    if hr:
        dist = {str(i): sum(1 for f in rows if f.rating == i) for i in range(1, 6)}
        summary = {"count": len(rows), "average": round(sum(f.rating for f in rows) / len(rows), 2) if rows else None,
                   "distribution": dist}
    return {"summary": summary, "items": items}
