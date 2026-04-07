from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.deps import CurrentAdmin
from app.models import AdminUser
from app.schemas.auth import ChangePasswordBody, LoginBody, ProfileUpdate, RefreshBody
from app.utils.responses import err, ok

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_INVALID_CREDENTIALS", "Invalid email or password"),
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_INVALID_CREDENTIALS", "Account is disabled"),
        )
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    access = create_access_token(user.id, extra={"role": user.role.value})
    refresh = create_refresh_token(user.id)
    return ok(
        {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role.value,
                "avatar_url": user.avatar_url,
            },
        }
    )


@router.post("/refresh")
def refresh_token(body: RefreshBody, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(
            body.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err("AUTH_TOKEN_INVALID", "Invalid refresh token"),
            )
        uid = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Invalid refresh token"),
        ) from None
    user = db.get(AdminUser, uid)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "User not found"),
        )
    access = create_access_token(user.id, extra={"role": user.role.value})
    new_refresh = create_refresh_token(user.id)
    return ok(
        {
            "access_token": access,
            "refresh_token": new_refresh,
            "expires_in": settings.access_token_expire_minutes * 60,
        }
    )


@router.post("/logout")
def logout(_: CurrentAdmin):
    return ok({"message": "Logged out"})


@router.get("/me")
def me(admin: CurrentAdmin):
    return ok(
        {
            "id": admin.id,
            "email": admin.email,
            "first_name": admin.first_name,
            "last_name": admin.last_name,
            "role": admin.role.value,
            "avatar_url": admin.avatar_url,
        }
    )


@router.put("/profile")
def update_profile(body: ProfileUpdate, admin: CurrentAdmin, db: Session = Depends(get_db)):
    if body.first_name is not None:
        admin.first_name = body.first_name
    if body.last_name is not None:
        admin.last_name = body.last_name
    if body.avatar_url is not None:
        admin.avatar_url = body.avatar_url
    db.commit()
    db.refresh(admin)
    return me(admin)


@router.put("/change-password")
def change_password(body: ChangePasswordBody, admin: CurrentAdmin, db: Session = Depends(get_db)):
    if body.new_password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Passwords do not match"),
        )
    if not verify_password(body.current_password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err("VALIDATION_ERROR", "Current password is incorrect"),
        )
    admin.password_hash = hash_password(body.new_password)
    db.commit()
    return ok({"message": "Password updated"})
