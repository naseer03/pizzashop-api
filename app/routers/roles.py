from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Employee, Permission, Role, RolePermission
from app.schemas.ops import RoleCreate, RolePermissionsBody
from app.utils.responses import err, ok

router = APIRouter(tags=["roles"])


def _perm_dict(p: Permission) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "code": p.code,
        "category": p.category,
        "description": p.description,
    }


def _role_dict(db: Session, r: Role) -> dict:
    emp_count = db.query(func.count(Employee.id)).filter(Employee.role_id == r.id).scalar()
    perms = [
        {"id": p.id, "code": p.code, "name": p.name}
        for p in sorted(r.permissions, key=lambda x: x.id)
    ]
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "color": r.color,
        "is_system_role": r.is_system_role,
        "employees_count": int(emp_count or 0),
        "permissions": perms,
    }


@router.get("/roles")
def list_roles(_: CurrentAdmin, db: Session = Depends(get_db)):
    rows = db.query(Role).order_by(Role.id).all()
    return ok([_role_dict(db, r) for r in rows])


@router.get("/roles/{role_id}")
def get_role(role_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Role not found"),
        )
    return ok(_role_dict(db, r))


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    r = Role(
        name=body.name,
        description=body.description,
        color=body.color,
        is_system_role=False,
    )
    db.add(r)
    db.flush()
    if body.permission_ids:
        for pid in body.permission_ids:
            if db.get(Permission, pid):
                db.add(RolePermission(role_id=r.id, permission_id=pid))
    db.commit()
    db.refresh(r)
    return ok(_role_dict(db, r))


@router.put("/roles/{role_id}")
def update_role(role_id: int, body: RoleCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Role not found"),
        )
    r.name = body.name
    r.description = body.description
    r.color = body.color
    if body.permission_ids is not None:
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        for pid in body.permission_ids:
            if db.get(Permission, pid):
                db.add(RolePermission(role_id=r.id, permission_id=pid))
    db.commit()
    db.refresh(r)
    return ok(_role_dict(db, r))


@router.put("/roles/{role_id}/permissions")
def update_role_permissions(
    role_id: int, body: RolePermissionsBody, _: CurrentAdmin, db: Session = Depends(get_db)
):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Role not found"),
        )
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for pid in body.permission_ids:
        if db.get(Permission, pid):
            db.add(RolePermission(role_id=r.id, permission_id=pid))
    db.commit()
    db.refresh(r)
    return ok(_role_dict(db, r))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Role not found"),
        )
    if r.is_system_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=err("PERMISSION_DENIED", "Cannot delete system role"),
        )
    db.delete(r)
    db.commit()
    return None


@router.get("/permissions")
def list_permissions(_: CurrentAdmin, db: Session = Depends(get_db)):
    rows = db.query(Permission).order_by(Permission.category, Permission.id).all()
    return ok([_perm_dict(p) for p in rows])
