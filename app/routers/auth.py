from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app import settings
from app.database import SessionLocal
from app.audit import (
    record_audit,
    ACTION_LOGIN,
    ACTION_LOGIN_FAILED,
    ENTITY_SESSION,
)
from app.models import User
from app.identity import resolve_employee, employee_identity


router = APIRouter(prefix="/auth", tags=["Authentication"])

password_hash = PasswordHash.recommended()

# Phase 10: from SMARTHR_SECRET_KEY (environment / .env.local), validated at
# import - so a missing key, or the old public development key in production,
# stops the application from starting rather than signing with it.
SECRET_KEY = settings.secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(user_id: int, role_id: int):
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "role_id": role_id,
        "exp": expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()

    # Failed sign-ins are recorded too. audit_logs.user_id is nullable, so an
    # attempt against an address with no account is stored with a null actor
    # rather than being dropped.
    if not user:
        record_audit(db, None, ACTION_LOGIN_FAILED, ENTITY_SESSION, None)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not password_hash.verify(form_data.password, user.password_hash):
        record_audit(db, user, ACTION_LOGIN_FAILED, ENTITY_SESSION, user.id)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        record_audit(db, user, ACTION_LOGIN_FAILED, ENTITY_SESSION, user.id)

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    token = create_access_token(user.id, user.role_id)

    record_audit(db, user, ACTION_LOGIN, ENTITY_SESSION, user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "role_id": user.role_id
    }


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = int(payload.get("sub"))

    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role_id": current_user.role_id,
        "is_active": current_user.is_active
    }


# =========================
# Who am I, as a person
#
# /auth/me answers with the account. This answers with the employee record
# linked to it, which is what every self-service page needs before it can
# scope anything to "me".
#
# employees.user_id is nullable, so an account with no employee row is a real
# state - it gets a 404 with an explanatory detail rather than an empty object
# the frontend would have to guess at.
# =========================

@router.get("/me/employee")
def get_my_employee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    employee = resolve_employee(current_user, db)

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"The account {current_user.email} is not linked to an employee "
                f"record. An administrator can link it on the Users page."
            )
        )

    return employee_identity(employee, db)
