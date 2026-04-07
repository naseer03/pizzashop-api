from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Crust
from app.schemas.menu import AvailabilityPatch, CrustCreate
from app.utils.responses import err, ok

router = APIRouter(prefix="/crusts", tags=["crusts"])


def _c_dict(c: Crust) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "price": float(c.price),
        "is_available": c.is_available,
        "sort_order": c.sort_order,
    }


@router.get("")
def list_crusts(_: CurrentAdmin, db: Session = Depends(get_db)):
    rows = db.query(Crust).order_by(Crust.sort_order, Crust.id).all()
    return ok([_c_dict(c) for c in rows])


@router.get("/{crust_id}")
def get_crust(crust_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Crust, crust_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Crust not found"),
        )
    return ok(_c_dict(c))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_crust(body: CrustCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = Crust(
        name=body.name,
        price=body.price,
        is_available=body.is_available,
        sort_order=body.sort_order,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return ok(_c_dict(c))


@router.put("/{crust_id}")
def update_crust(crust_id: int, body: CrustCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Crust, crust_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Crust not found"),
        )
    c.name = body.name
    c.price = body.price
    c.is_available = body.is_available
    c.sort_order = body.sort_order
    db.commit()
    db.refresh(c)
    return ok(_c_dict(c))


@router.patch("/{crust_id}/availability")
def patch_crust_availability(
    crust_id: int, body: AvailabilityPatch, _: CurrentAdmin, db: Session = Depends(get_db)
):
    c = db.get(Crust, crust_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Crust not found"),
        )
    c.is_available = body.is_available
    db.commit()
    db.refresh(c)
    return ok(_c_dict(c))


@router.delete("/{crust_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crust(crust_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Crust, crust_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Crust not found"),
        )
    db.delete(c)
    db.commit()
    return None
