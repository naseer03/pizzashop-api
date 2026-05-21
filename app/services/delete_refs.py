"""Pre-delete reference checks and category cascade helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Category,
    Crust,
    Employee,
    MenuItem,
    OrderItem,
    OrderItemTopping,
    Role,
    Topping,
)
from app.services.catalog_categories import detach_category_from_toppings_and_crusts
from app.utils.menu_images import try_remove_stored_menu_image
from app.utils.responses import err


def deleted_payload(resource_id: int) -> dict:
    return {"id": resource_id, "deleted": True}


def ensure_menu_item_deletable(db: Session, menu_item_id: int) -> None:
    count = (
        db.query(func.count(OrderItem.id))
        .filter(OrderItem.menu_item_id == menu_item_id)
        .scalar()
        or 0
    )
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err(
                "RESOURCE_IN_USE",
                "This menu item is used in existing orders and cannot be deleted.",
            ),
        )


def ensure_topping_deletable(db: Session, topping_id: int) -> None:
    count = (
        db.query(func.count(OrderItemTopping.id))
        .filter(OrderItemTopping.topping_id == topping_id)
        .scalar()
        or 0
    )
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err(
                "RESOURCE_IN_USE",
                "This topping is used in existing orders and cannot be deleted.",
            ),
        )


def ensure_crust_deletable(db: Session, crust_id: int) -> None:
    count = (
        db.query(func.count(OrderItem.id))
        .filter(OrderItem.crust_id == crust_id)
        .scalar()
        or 0
    )
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err(
                "RESOURCE_IN_USE",
                "This crust is used in existing orders and cannot be deleted.",
            ),
        )


def ensure_role_deletable(db: Session, role: Role) -> None:
    count = (
        db.query(func.count(Employee.id)).filter(Employee.role_id == role.id).scalar() or 0
    )
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err(
                "RESOURCE_IN_USE",
                f"Cannot delete role: {count} employee(s) still use this role.",
                details={"employees_count": int(count)},
            ),
        )


def clear_subcategory_on_menu_items(db: Session, subcategory_id: int) -> None:
    db.query(MenuItem).filter(MenuItem.subcategory_id == subcategory_id).update(
        {MenuItem.subcategory_id: None},
        synchronize_session=False,
    )


def delete_category_with_dependents(db: Session, category: Category) -> None:
    menu_items = db.query(MenuItem).filter(MenuItem.category_id == category.id).all()
    if menu_items:
        item_ids = [mi.id for mi in menu_items]
        used_ids = {
            row[0]
            for row in db.query(OrderItem.menu_item_id)
            .filter(OrderItem.menu_item_id.in_(item_ids))
            .distinct()
            .all()
        }
        if used_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err(
                    "RESOURCE_IN_USE",
                    "Cannot delete category: one or more menu items are used in existing orders.",
                    details={"menu_item_ids": sorted(used_ids)},
                ),
            )
        for mi in menu_items:
            try_remove_stored_menu_image(mi.image_url)
            db.delete(mi)

    detach_category_from_toppings_and_crusts(db, category.id)
    db.delete(category)
