import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee, User
from ..schemas import ChangePasswordIn, LoginIn, RegisterIn
from ..security import create_token, current_user, hash_password, verify_password
from ..services import default_onboarding, init_balances, my_employee, notify

router = APIRouter(prefix="/api/auth", tags=["Auth"])
_attempts: dict = {}  # email -> [timestamps]; simple brute-force throttle


def _profile(db, user):
    emp = my_employee(db, user)
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role,
            "employee_id": emp.id if emp else None, "name": emp.name if emp else user.email,
            "department": emp.department if emp else None}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    key, now = body.email.lower(), time.time()
    recent = [t for t in _attempts.get(key, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(or_(User.email == key, User.username == key)))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        recent.append(now)
        _attempts[key] = recent
        raise HTTPException(401, "Incorrect email or password")
    _attempts.pop(key, None)
    return {"access_token": create_token(user), "token_type": "bearer", "user": _profile(db, user)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Public sign-up. Always creates an EMPLOYEE; roles can only be changed by an admin."""
    email, username = body.email.lower(), body.username.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "This email is already registered")
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, "This username is taken")
    u = User(username=username, email=email, password_hash=hash_password(body.password), role="employee")
    db.add(u)
    db.flush()
    e = Employee(user_id=u.id, name=body.full_name, email=email, department="General", designation="New joiner")
    db.add(e)
    db.flush()
    init_balances(db, e.id)
    default_onboarding(db, e)
    notify(db, u.id, "Welcome to WorkSphere", "Your account is ready. HR will assign your shift.", "info")
    db.commit()
    return {"access_token": create_token(u), "token_type": "bearer", "user": _profile(db, u)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _profile(db, user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
