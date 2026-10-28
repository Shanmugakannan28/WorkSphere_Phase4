import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except ValueError:
        return False


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp},
                      settings.secret_key, algorithm=settings.algorithm)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        data = jwt.decode(creds.credentials, settings.secret_key, algorithms=[settings.algorithm])
        user = db.get(User, int(data["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    if not user or not user.is_active:
        raise HTTPException(401, "Account disabled")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission to do this")
        return user
    return dep
