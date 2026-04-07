from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Topping, ToppingCategory
from app.schemas.menu import AvailabilityPatch, ToppingCreate
from app.utils.responses import err, ok

router = APIRouter(prefix="/toppings", tags=["toppings"])


def _t_dict(t: Topping) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "category": t.category.value,
        "price": float(t.price),
        "is_available": t.is_available,
        "sort_order": t.sort_order,
    }


@router.get("")
def list_toppings(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    category: Annotated[str | None, Query()] = None,
    is_available: Annotated[bool | None, Query()] = None,
):
    q = db.query(Topping).order_by(Topping.sort_order, Topping.id)
    if category:
        try:
            q = q.filter(Topping.category == ToppingCategory(category))
        except ValueError:
            pass
    if is_available is not None:
        q = q.filter(Topping.is_available == is_available)
    return ok([_t_dict(t) for t in q.all()])


@router.get("/{topping_id}")
def get_topping(topping_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    return ok(_t_dict(t))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_topping(body: ToppingCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    try:
        cat = ToppingCategory(body.category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid topping category"),
        ) from None
    t = Topping(
        name=body.name,
        category=cat,
        price=body.price,
        is_available=body.is_available,
        sort_order=body.sort_order,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return ok(_t_dict(t))


@router.put("/{topping_id}")
def update_topping(topping_id: int, body: ToppingCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    try:
        t.category = ToppingCategory(body.category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid topping category"),
        ) from None
    t.name = body.name
    t.price = body.price
    t.is_available = body.is_available
    t.sort_order = body.sort_order
    db.commit()
    db.refresh(t)
    return ok(_t_dict(t))


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
    return ok(_t_dict(t))


@router.delete("/{topping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topping(topping_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    t = db.get(Topping, topping_id)
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Topping not found"),
        )
    db.delete(t)
    db.commit()
    return None
