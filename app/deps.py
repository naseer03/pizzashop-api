from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import AdminUser, Employee, EmployeeStatus, Role
from app.utils.responses import err

security = HTTPBearer(auto_error=False)


def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Missing bearer token"),
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err("AUTH_TOKEN_INVALID", "Invalid token type"),
            )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err("AUTH_TOKEN_INVALID", "Invalid token payload"),
            )
        user_id = int(sub)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_EXPIRED", "Access token has expired"),
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Invalid or malformed token"),
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Invalid subject"),
        ) from None

    user = db.get(AdminUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "User not found or inactive"),
        )
    return user


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]


@dataclass
class CashierPrincipal:
    employee: Employee
    permission_codes: set[str]


def get_cashier_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> CashierPrincipal:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Missing bearer token"),
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access" or payload.get("principal") != "employee":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err("AUTH_TOKEN_INVALID", "Invalid token for cashier"),
            )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err("AUTH_TOKEN_INVALID", "Invalid token payload"),
            )
        raw = str(sub)
        if not raw.startswith("emp:"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err("AUTH_TOKEN_INVALID", "Invalid token for cashier"),
            )
        employee_id = int(raw.split(":", 1)[1])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_EXPIRED", "Access token has expired"),
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Invalid or malformed token"),
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Invalid subject"),
        ) from None

    employee = (
        db.query(Employee)
        .options(joinedload(Employee.role).joinedload(Role.permissions))
        .filter(Employee.id == employee_id)
        .first()
    )
    if not employee or employee.status != EmployeeStatus.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_TOKEN_INVALID", "Employee not found or inactive"),
        )
    codes = {p.code for p in (employee.role.permissions or [])}
    return CashierPrincipal(employee=employee, permission_codes=codes)


CashierAuth = Annotated[CashierPrincipal, Depends(get_cashier_principal)]


class RequireCashierPermissions:
    def __init__(self, *codes: str) -> None:
        self.codes = codes

    def __call__(self, principal: CashierAuth) -> CashierPrincipal:
        missing = [c for c in self.codes if c not in principal.permission_codes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=err("PERMISSION_DENIED", "Missing required permissions", {"missing": missing}),
            )
        return principal
