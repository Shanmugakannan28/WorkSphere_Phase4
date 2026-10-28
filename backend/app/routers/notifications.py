from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User
from ..security import current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read == False)) or 0  # noqa: E712
    items = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(60))
    return {"unread": unread, "items": [{"id": n.id, "title": n.title, "message": n.message, "type": n.type,
                                         "is_read": n.is_read, "created_at": n.created_at} for n in items]}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/{nid}/read")
def read_one(nid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}
