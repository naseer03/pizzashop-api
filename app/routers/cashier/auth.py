from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, verify_password
from app.config import settings
from app.database import get_db
from app.models import Employee, EmployeeStatus, Role
from app.schemas.cashier import CashierLoginBody
from app.utils.responses import err, ok

router = APIRouter()


def _employee_pos_allowed(emp: Employee) -> bool:
    role_name = (emp.role.name or "").lower()
    if "cashier" in role_name or "manager" in role_name:
        return True
    codes = {p.code for p in (emp.role.permissions or [])}
    return "orders.create" in codes or "orders.update" in codes


@router.post("/login")
def cashier_login(body: CashierLoginBody, db: Session = Depends(get_db)):
    emp = (
        db.query(Employee)
        .options(joinedload(Employee.role).joinedload(Role.permissions))
        .filter(Employee.email == str(body.email))
        .first()
    )
    if not emp or not emp.password_hash or not verify_password(body.password, emp.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_INVALID_CREDENTIALS", "Invalid email or password"),
        )
    if emp.status != EmployeeStatus.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err("AUTH_INVALID_CREDENTIALS", "Employee account is not active"),
        )
    if not _employee_pos_allowed(emp):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=err("AUTH_ROLE_NOT_ALLOWED", "This account is not permitted to use the cashier POS"),
        )

    codes = sorted({p.code for p in (emp.role.permissions or [])})
    subject = f"emp:{emp.id}"
    access = create_access_token(
        subject,
        extra={
            "principal": "employee",
            "role": emp.role.name,
            "permissions": codes,
        },
    )
    return ok(
        {
            "access_token": access,
            "expires_in": settings.access_token_expire_minutes * 60,
            "token_type": "bearer",
            "employee": {
                "id": emp.id,
                "email": emp.email,
                "first_name": emp.first_name,
                "last_name": emp.last_name,
                "role": {"id": emp.role.id, "name": emp.role.name},
                "permissions": codes,
            },
        }
    )
