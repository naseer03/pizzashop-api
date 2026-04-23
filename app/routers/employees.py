from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database import get_db
from app.deps import CurrentAdmin
from app.models import DayOfWeek, Employee, EmployeeSchedule, EmployeeStatus, Role
from app.schemas.ops import EmployeeCreate, EmployeeScheduleBody, EmployeeStatusPatch
from app.utils.responses import err, ok

router = APIRouter(prefix="/employees", tags=["employees"])


def _parse_time(v: object) -> time:
    s = v if isinstance(v, str) else "09:00"
    parts = s.split(":")
    h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    return time(h, m)


def _emp_dict(e: Employee) -> dict:
    role = e.role
    role_out = (
        {"id": role.id, "name": role.name, "color": role.color}
        if role is not None
        else {"id": e.role_id, "name": "", "color": "#6B7280"}
    )
    return {
        "id": e.id,
        "employee_code": e.employee_code,
        "first_name": e.first_name,
        "last_name": e.last_name,
        "email": e.email,
        "phone": e.phone,
        "avatar_url": e.avatar_url,
        "role": role_out,
        "hourly_rate": float(e.hourly_rate),
        "status": e.status.value,
        "has_password": bool(e.password_hash),
        "hire_date": e.hire_date.isoformat() if e.hire_date else None,
        "schedule": [
            {
                "day": sch.day_of_week.value,
                "start_time": sch.start_time.strftime("%H:%M"),
                "end_time": sch.end_time.strftime("%H:%M"),
            }
            for sch in sorted(
                e.schedules,
                key=lambda x: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(
                    x.day_of_week.value
                ),
            )
        ],
    }


def _next_emp_code(db: Session) -> str:
    last = db.query(Employee).order_by(Employee.id.desc()).first()
    n = (last.id + 1) if last else 1
    return f"EMP{n:03d}"


@router.get("")
def list_employees(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    role_id: Annotated[int | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
):
    q = db.query(Employee)
    if status_filter:
        try:
            q = q.filter(Employee.status == EmployeeStatus(status_filter))
        except ValueError:
            pass
    if role_id is not None:
        q = q.filter(Employee.role_id == role_id)
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Employee.first_name.like(term),
                Employee.last_name.like(term),
                Employee.email.like(term),
            )
        )
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return ok(
        {
            "employees": [_emp_dict(e) for e in rows],
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total,
                "total_pages": total_pages,
            },
        }
    )


@router.get("/{employee_id}")
def get_employee(employee_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Employee not found"),
        )
    return ok(_emp_dict(e))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    if not db.get(Role, body.role_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("RESOURCE_NOT_FOUND", "Role not found"),
        )
    e = Employee(
        employee_code=_next_emp_code(db),
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
        role_id=body.role_id,
        hourly_rate=body.hourly_rate,
        hire_date=body.hire_date,
        date_of_birth=body.date_of_birth,
        address=body.address,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
        password_hash=hash_password(body.password) if body.password else None,
    )
    db.add(e)
    db.flush()
    if body.schedule:
        for block in body.schedule:
            try:
                day = DayOfWeek(block["day"])
            except (ValueError, KeyError):
                continue
            db.add(
                EmployeeSchedule(
                    employee_id=e.id,
                    day_of_week=day,
                    start_time=_parse_time(block.get("start_time", "09:00")),
                    end_time=_parse_time(block.get("end_time", "17:00")),
                )
            )
    db.commit()
    db.refresh(e)
    return ok(_emp_dict(e))


@router.put("/{employee_id}")
def update_employee(employee_id: int, body: EmployeeCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Employee not found"),
        )
    e.first_name = body.first_name
    e.last_name = body.last_name
    e.email = body.email
    e.phone = body.phone
    e.role_id = body.role_id
    e.hourly_rate = body.hourly_rate
    e.hire_date = body.hire_date
    e.date_of_birth = body.date_of_birth
    e.address = body.address
    e.emergency_contact_name = body.emergency_contact_name
    e.emergency_contact_phone = body.emergency_contact_phone
    if body.password is not None:
        e.password_hash = hash_password(body.password) if body.password else None
    if body.schedule is not None:
        for s in e.schedules:
            db.delete(s)
        db.flush()
        for block in body.schedule:
            try:
                day = DayOfWeek(block["day"])
            except (ValueError, KeyError):
                continue
            db.add(
                EmployeeSchedule(
                    employee_id=e.id,
                    day_of_week=day,
                    start_time=_parse_time(block.get("start_time", "09:00")),
                    end_time=_parse_time(block.get("end_time", "17:00")),
                )
            )
    db.commit()
    db.refresh(e)
    return ok(_emp_dict(e))


@router.patch("/{employee_id}/status")
def patch_employee_status(
    employee_id: int, body: EmployeeStatusPatch, _: CurrentAdmin, db: Session = Depends(get_db)
):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Employee not found"),
        )
    try:
        e.status = EmployeeStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid status"),
        ) from None
    db.commit()
    db.refresh(e)
    return ok(_emp_dict(e))


@router.put("/{employee_id}/schedule")
def put_schedule(employee_id: int, body: EmployeeScheduleBody, _: CurrentAdmin, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Employee not found"),
        )
    for s in e.schedules:
        db.delete(s)
    db.flush()
    if body.schedule:
        for block in body.schedule:
            try:
                day = DayOfWeek(block["day"])
            except (ValueError, KeyError):
                continue
            db.add(
                EmployeeSchedule(
                    employee_id=e.id,
                    day_of_week=day,
                    start_time=_parse_time(block.get("start_time", "09:00")),
                    end_time=_parse_time(block.get("end_time", "17:00")),
                )
            )
    db.commit()
    db.refresh(e)
    return ok(_emp_dict(e))


@router.delete("/{employee_id}")
def deactivate_employee(employee_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Employee not found"),
        )
    e.status = EmployeeStatus.inactive
    db.commit()
    db.refresh(e)
    return ok({"id": e.id, "status": e.status.value})
