from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Crust
from app.schemas.menu import AvailabilityPatch, CrustCreate
from app.services.cashier_menu import invalidate_menu_cache
from app.services.catalog_categories import (
    assign_crust_categories,
    crust_item_dict,
    filter_crusts_by_category,
    group_crusts_by_category,
)
from app.services.delete_refs import deleted_payload, ensure_crust_deletable
from app.utils.responses import err, ok

router = APIRouter(prefix="/crusts", tags=["crusts"])


def _crust_query(db: Session):
    return db.query(Crust).options(joinedload(Crust.category)).order_by(Crust.sort_order, Crust.id)


@router.get("")
def list_crusts(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    category_id: Annotated[int | None, Query(description="Filter by menu category id")] = None,
):
    q = _crust_query(db)
    if category_id is not None:
        q = filter_crusts_by_category(q, category_id)
    return ok({"categories": group_crusts_by_category(db, q.all())})


@router.get("/{crust_id}")
def get_crust(crust_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = _crust_query(db).filter(Crust.id == crust_id).first()
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Crust not found"),
        )
    return ok(crust_item_dict(db, c))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_crust(body: CrustCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = Crust(
        name=body.name,
        category_id=None,
        price=body.price,
        is_available=body.is_available,
        sort_order=body.sort_order,
    )
    db.add(c)
    db.flush()
    assign_crust_categories(db, c, body.category_ids)
    db.commit()
    c = _crust_query(db).filter(Crust.id == c.id).one()
    invalidate_menu_cache()
    return ok(crust_item_dict(db, c))


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
    assign_crust_categories(db, c, body.category_ids)
    db.commit()
    db.refresh(c)
    invalidate_menu_cache()
    return ok(crust_item_dict(db, c))


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
    invalidate_menu_cache()
    return ok(crust_item_dict(db, c))


@router.delete("/{crust_id}")
def delete_crust(crust_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Crust, crust_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Crust not found"),
        )
    ensure_crust_deletable(db, crust_id)
    db.delete(c)
    db.commit()
    invalidate_menu_cache()
    return ok(deleted_payload(crust_id))
