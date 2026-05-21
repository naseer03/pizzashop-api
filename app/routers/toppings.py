from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Topping
from app.schemas.menu import AvailabilityPatch, ToppingCreate
from app.services.cashier_menu import invalidate_menu_cache
from app.services.catalog_categories import (
    assign_topping_categories,
    group_toppings_by_category,
    topping_item_dict,
)
from app.services.delete_refs import deleted_payload, ensure_topping_deletable
from app.utils.responses import err, ok

router = APIRouter(prefix="/toppings", tags=["toppings"])


@router.get("")
def list_toppings(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    category_id: Annotated[int | None, Query(description="Filter by menu category id")] = None,
    is_available: Annotated[bool | None, Query()] = None,
):
    q = db.query(Topping).order_by(Topping.sort_order, Topping.id)
    if category_id is not None:
        q = q.filter(Topping.category_id == category_id)
    if is_available is not None:
        q = q.filter(Topping.is_available == is_available)
    rows = q.all()
    return ok({"categories": group_toppings_by_category(db, rows)})


@router.get("/{topping_id}")
def get_topping(topping_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    return ok(topping_item_dict(db, t))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_topping(body: ToppingCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = Topping(
        name=body.name,
        category_id=body.category_ids[0],
        price=body.price,
        is_available=body.is_available,
        sort_order=body.sort_order,
    )
    assign_topping_categories(db, t, body.category_ids)
    db.add(t)
    db.commit()
    db.refresh(t)
    invalidate_menu_cache()
    return ok(topping_item_dict(db, t))


@router.put("/{topping_id}")
def update_topping(topping_id: int, body: ToppingCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    t.name = body.name
    t.price = body.price
    t.is_available = body.is_available
    t.sort_order = body.sort_order
    assign_topping_categories(db, t, body.category_ids)
    db.commit()
    db.refresh(t)
    invalidate_menu_cache()
    return ok(topping_item_dict(db, t))


@router.patch("/{topping_id}/availability")
def patch_topping_availability(
    topping_id: int, body: AvailabilityPatch, _: CurrentAdmin, db: Session = Depends(get_db)
):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    t.is_available = body.is_available
    db.commit()
    db.refresh(t)
    invalidate_menu_cache()
    return ok(topping_item_dict(db, t))


@router.delete("/{topping_id}")
def delete_topping(topping_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    ensure_topping_deletable(db, topping_id)
    db.delete(t)
    db.commit()
    invalidate_menu_cache()
    return ok(deleted_payload(topping_id))
