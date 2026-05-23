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
    list_crust_items,
    list_topping_items,
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
    group_by_category: Annotated[
        bool,
        Query(
            description=(
                "If true, nest toppings under each linked category. Default false (flat list)."
            ),
        ),
    ] = False,
):
    q = db.query(Topping).order_by(Topping.sort_order, Topping.id)
    if only_available:
        q = q.filter(Topping.is_available.is_(True))
    if category_id is not None:
        q = filter_toppings_by_category(q, category_id)
    rows = q.all()
    if group_by_category:
        return ok({"categories": group_toppings_by_category(db, rows)})
    return ok({"toppings": list_topping_items(db, rows)})


@crusts_router.get("")
def get_crusts(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
    only_available: Annotated[bool, Query()] = True,
    category_id: Annotated[int | None, Query(description="Filter by menu category id")] = None,
    group_by_category: Annotated[
        bool,
        Query(
            description=(
                "If true, nest crusts under each linked category. Default false (flat list)."
            ),
        ),
    ] = False,
):
    q = db.query(Crust).options(joinedload(Crust.category)).order_by(Crust.sort_order, Crust.id)
    if only_available:
        q = q.filter(Crust.is_available.is_(True))
    if category_id is not None:
        q = filter_crusts_by_category(q, category_id)
    rows = q.all()
    if group_by_category:
        return ok({"categories": group_crusts_by_category(db, rows)})
    return ok({"crusts": list_crust_items(db, rows)})
