from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Announcement, Employee, User
from ..schemas import AnnouncementIn
from ..security import current_user, require_roles
from ..services import notify

router = APIRouter(prefix="/api/announcements", tags=["Announcements"])


def _ser(a: Announcement, names: dict, full=True):
    return {"id": a.id, "title": a.title, "message": a.message if full else a.message[:160],
            "author": names.get(a.created_by, "HR"), "pinned": a.pinned, "created_at": a.created_at}


def _names(db):
    return {e.user_id: e.name for e in db.scalars(select(Employee))}


@router.get("")
def list_announcements(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(current_user)):
    names = _names(db)
    rows = db.scalars(select(Announcement).order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).limit(limit))
    return [_ser(a, names, full=False) for a in rows]


@router.get("/{aid}")
def get_announcement(aid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Announcement, aid)
    if not a:
        raise HTTPException(404, "Announcement not found")
    return _ser(a, _names(db))


@router.post("", status_code=201)
def post_announcement(body: AnnouncementIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    a = Announcement(title=body.title, message=body.message, pinned=body.pinned, created_by=user.id)
    db.add(a)
    for uid in db.scalars(select(User.id).where(User.is_active == True, User.id != user.id)):  # noqa: E712
        notify(db, uid, "New announcement", body.title, "announcement")
    db.commit()
    return {"id": a.id}


@router.delete("/{aid}")
def delete_announcement(aid: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "hr"))):
    a = db.get(Announcement, aid)
    if not a:
        raise HTTPException(404, "Announcement not found")
    db.delete(a)
    db.commit()
    return {"ok": True}
