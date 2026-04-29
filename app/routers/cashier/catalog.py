from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.models import Category, Crust, Topping
from app.utils.responses import ok

toppings_router = APIRouter()
crusts_router = APIRouter()


def _topping_dict(db: Session, topping: Topping) -> dict:
    cat = db.get(Category, topping.category_id)
    return {
        "id": topping.id,
        "name": topping.name,
        "category": {
            "id": cat.id if cat else topping.category_id,
            "name": cat.name if cat else "",
        },
        "price": float(topping.price),
        "is_available": topping.is_available,
        "sort_order": topping.sort_order,
    }


def _crust_dict(crust: Crust) -> dict:
    return {
        "id": crust.id,
        "name": crust.name,
        "category": (
            {"id": crust.category_id, "name": crust.category.name if crust.category else ""}
            if crust.category_id
            else None
        ),
        "price": float(crust.price),
        "is_available": crust.is_available,
        "sort_order": crust.sort_order,
    }


@toppings_router.get("")
def get_toppings(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
    only_available: Annotated[bool, Query()] = True,
):
    q = db.query(Topping).order_by(Topping.sort_order, Topping.id)
    if only_available:
        q = q.filter(Topping.is_available.is_(True))
    return ok({"toppings": [_topping_dict(db, topping) for topping in q.all()]})


@crusts_router.get("")
def get_crusts(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
    only_available: Annotated[bool, Query()] = True,
):
    q = db.query(Crust).order_by(Crust.sort_order, Crust.id)
    if only_available:
        q = q.filter(Crust.is_available.is_(True))
    return ok({"crusts": [_crust_dict(crust) for crust in q.all()]})
