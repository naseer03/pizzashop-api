from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.services import cashier_menu
from app.utils.responses import err, ok

categories_router = APIRouter()


@categories_router.get("")
def get_categories(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
):
    return ok({"categories": cashier_menu.categories_payload(db)})


menu_router = APIRouter()


@menu_router.get("")
def get_menu(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
    only_available: Annotated[bool, Query()] = True,
):
    items = cashier_menu.menu_list_payload(db, only_available=only_available)
    return ok({"items": items})


@menu_router.get("/{item_id}")
def get_menu_item(
    item_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
):
    row = cashier_menu.menu_item_payload(db, item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
        )
    return ok(row)
