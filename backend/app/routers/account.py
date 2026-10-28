from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import MUTABLE_TYPES, PrefsIn, ProfileIn
from ..security import current_user
from ..services import my_employee

router = APIRouter(prefix="/api/account", tags=["Profile & settings"])


def _view(db, user):
    e = my_employee(db, user)
    return {"username": user.username, "email": user.email, "role": user.role,
            "name": e.name if e else None, "phone": e.phone if e else None, "address": e.address if e else None,
            "department": e.department if e else None, "designation": e.designation if e else None,
            "preferences": {"pref_inapp": user.pref_inapp, "pref_email": user.pref_email,
                            "muted_types": [t for t in (user.muted_types or "").split(",") if t]},
            "mutable_types": MUTABLE_TYPES}


@router.get("")
def get_account(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _view(db, user)


@router.put("/profile")
def update_profile(body: ProfileIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = my_employee(db, user)
    if not e:
        raise HTTPException(400, "No employee profile is linked to this account")
    data = body.model_dump(exclude_unset=True)
    if data.get("name"):
        e.name = data["name"]
    if "phone" in data:
        e.phone = data["phone"] or None
    if "address" in data:
        e.address = data["address"] or None
    db.commit()
    return _view(db, user)


@router.put("/preferences")
def update_preferences(body: PrefsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user.pref_inapp, user.pref_email = body.pref_inapp, body.pref_email
    user.muted_types = ",".join(body.muted_types)
    db.commit()
    return _view(db, user)
