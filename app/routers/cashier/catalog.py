from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.models import Crust, Topping
from app.services.catalog_categories import (
    filter_crusts_by_category,
    filter_toppings_by_category,
    group_crusts_by_category,
    group_toppings_by_category,
)
from app.utils.responses import ok

toppings_router = APIRouter()
crusts_router = APIRouter()


@toppings_router.get("")
def get_toppings(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
    only_available: Annotated[bool, Query()] = True,
    category_id: Annotated[int | None, Query(description="Filter by menu category id")] = None,
):
    q = db.query(Topping).order_by(Topping.sort_order, Topping.id)
    if only_available:
        q = q.filter(Topping.is_available.is_(True))
    if category_id is not None:
        q = filter_toppings_by_category(q, category_id)
    return ok({"categories": group_toppings_by_category(db, q.all())})


@crusts_router.get("")
def get_crusts(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
    only_available: Annotated[bool, Query()] = True,
    category_id: Annotated[int | None, Query(description="Filter by menu category id")] = None,
):
    q = db.query(Crust).options(joinedload(Crust.category)).order_by(Crust.sort_order, Crust.id)
    if only_available:
        q = q.filter(Crust.is_available.is_(True))
    if category_id is not None:
        q = filter_crusts_by_category(q, category_id)
    return ok({"categories": group_crusts_by_category(db, q.all())})
