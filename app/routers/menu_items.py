from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Category, MenuItem, MenuItemSize, SizeName
from app.schemas.menu import AvailabilityPatch, MenuItemCreate, MenuItemUpdate, MenuSizeIn
from app.services.cashier_menu import invalidate_menu_cache
from app.services.menu_payloads import menu_item_to_dict
from app.utils.menu_images import save_menu_item_image, try_remove_stored_menu_image
from app.utils.responses import err, ok
from app.utils.slug import slugify

router = APIRouter(prefix="/menu-items", tags=["menu-items"])


def _item_dict(db: Session, mi: MenuItem) -> dict:
    return menu_item_to_dict(db, mi)


def _parse_sizes_form(raw: str | None, *, required: bool) -> list[MenuSizeIn] | None:
    if raw is None:
        if required:
            return []
        return None
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", f"sizes must be a valid JSON array: {exc.msg}"),
        ) from None
    if not isinstance(loaded, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "sizes must be a JSON array."),
        )
    return TypeAdapter(list[MenuSizeIn]).validate_python(loaded)


@router.get("")
def list_menu_items(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    category_id: Annotated[int | None, Query()] = None,
    subcategory_id: Annotated[int | None, Query()] = None,
    is_available: Annotated[bool | None, Query()] = None,
    is_featured: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
):
    q = db.query(MenuItem)
    if category_id is not None:
        q = q.filter(MenuItem.category_id == category_id)
    if subcategory_id is not None:
        q = q.filter(MenuItem.subcategory_id == subcategory_id)
    if is_available is not None:
        q = q.filter(MenuItem.is_available == is_available)
    if is_featured is not None:
        q = q.filter(MenuItem.is_featured == is_featured)
    if search:
        q = q.filter(MenuItem.name.like(f"%{search}%"))
    total = q.count()
    rows = q.order_by(MenuItem.display_order, MenuItem.id).offset((page - 1) * per_page).limit(per_page).all()
    items = [_item_dict(db, mi) for mi in rows]
    total_pages = max(1, (total + per_page - 1) // per_page)
    return ok(
        {
            "items": items,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total,
                "total_pages": total_pages,
            },
        }
    )


@router.get("/{item_id}")
def get_menu_item(item_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    mi = db.get(MenuItem, item_id)
    if not mi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
        )
    return ok(_item_dict(db, mi))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create menu item",
    description=(
        "Create a menu item via multipart/form-data. Send structured fields and optional image file in one request. "
        "For `sizes`, pass a JSON array string, e.g. "
        "`[{\"size\":\"small\",\"price\":10.99,\"is_default\":false}]`."
    ),
)
async def create_menu_item(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    name: str = Form(...),
    category_id: int = Form(...),
    base_price: float = Form(...),
    description: str | None = Form(None),
    subcategory_id: int | None = Form(None),
    sizes: str | None = Form("[]"),
    is_available: bool = Form(True),
    is_featured: bool = Form(False),
    preparation_time_minutes: int = Form(15),
    calories: int | None = Form(None),
    allergens: str | None = Form(None),
    image: UploadFile | None = File(None),
):
    sizes_parsed = _parse_sizes_form(sizes, required=True)
    body = MenuItemCreate(
        name=name,
        description=description,
        category_id=category_id,
        subcategory_id=subcategory_id,
        base_price=base_price,
        sizes=sizes_parsed or [],
        is_available=is_available,
        is_featured=is_featured,
        preparation_time_minutes=preparation_time_minutes,
        calories=calories,
        allergens=allergens,
    )

    if not db.get(Category, body.category_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid category_id"),
        )

    slug = slugify(body.name)
    base = slug
    n = 0
    while db.query(MenuItem).filter(MenuItem.slug == slug).first():
        n += 1
        slug = f"{base}-{n}"

    mi = MenuItem(
        name=body.name,
        slug=slug,
        description=body.description,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        base_price=body.base_price,
        image_url=None,
        is_available=body.is_available,
        is_featured=body.is_featured,
        preparation_time_minutes=body.preparation_time_minutes,
        calories=body.calories,
        allergens=body.allergens,
    )
    db.add(mi)
    db.flush()

    for s in body.sizes:
        try:
            sn = SizeName(s.size)
        except ValueError:
            continue
        db.add(
            MenuItemSize(
                menu_item_id=mi.id,
                size_name=sn,
                price=s.price,
                is_default=s.is_default,
            )
        )

    db.commit()

    if image is not None:
        mi.image_url = await save_menu_item_image(image)
        db.commit()

    db.refresh(mi)
    invalidate_menu_cache(mi.id)
    return ok(_item_dict(db, mi))


@router.put(
    "/{item_id}",
    summary="Update menu item",
    description=(
        "Update a menu item via multipart/form-data. Include only fields you want to change. "
        "For `sizes`, pass a JSON array string to replace all sizes. Include `image` file to replace image."
    ),
)
async def update_menu_item(
    item_id: int,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    name: str | None = Form(None),
    description: str | None = Form(None),
    category_id: int | None = Form(None),
    subcategory_id: int | None = Form(None),
    base_price: float | None = Form(None),
    sizes: str | None = Form(None),
    is_available: bool | None = Form(None),
    is_featured: bool | None = Form(None),
    preparation_time_minutes: int | None = Form(None),
    calories: int | None = Form(None),
    allergens: str | None = Form(None),
    image: UploadFile | None = File(None),
):
    mi = db.get(MenuItem, item_id)
    if not mi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
        )

    sizes_parsed = _parse_sizes_form(sizes, required=False)
    body = MenuItemUpdate(
        name=name,
        description=description,
        category_id=category_id,
        subcategory_id=subcategory_id,
        base_price=base_price,
        sizes=sizes_parsed,
        is_available=is_available,
        is_featured=is_featured,
        preparation_time_minutes=preparation_time_minutes,
        calories=calories,
        allergens=allergens,
    )

    if body.name is not None:
        mi.name = body.name
        mi.slug = slugify(body.name)
    if body.description is not None:
        mi.description = body.description
    if body.category_id is not None:
        mi.category_id = body.category_id
    if body.subcategory_id is not None:
        mi.subcategory_id = body.subcategory_id
    if body.base_price is not None:
        mi.base_price = body.base_price
    if body.is_available is not None:
        mi.is_available = body.is_available
    if body.is_featured is not None:
        mi.is_featured = body.is_featured
    if body.preparation_time_minutes is not None:
        mi.preparation_time_minutes = body.preparation_time_minutes
    if body.calories is not None:
        mi.calories = body.calories
    if body.allergens is not None:
        mi.allergens = body.allergens

    if body.sizes is not None:
        for s in mi.sizes:
            db.delete(s)
        db.flush()
        for s in body.sizes:
            try:
                sn = SizeName(s.size)
            except ValueError:
                continue
            db.add(
                MenuItemSize(
                    menu_item_id=mi.id,
                    size_name=sn,
                    price=s.price,
                    is_default=s.is_default,
                )
            )

    if image is not None:
        new_url = await save_menu_item_image(image)
        old_url = mi.image_url
        mi.image_url = new_url
        try_remove_stored_menu_image(old_url)

    db.commit()
    db.refresh(mi)
    invalidate_menu_cache(mi.id)
    return ok(_item_dict(db, mi))


@router.patch("/{item_id}/availability")
def patch_availability(item_id: int, body: AvailabilityPatch, _: CurrentAdmin, db: Session = Depends(get_db)):
    mi = db.get(MenuItem, item_id)
    if not mi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
        )
    mi.is_available = body.is_available
    db.commit()
    db.refresh(mi)
    invalidate_menu_cache(mi.id)
    return ok(_item_dict(db, mi))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_item(item_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    mi = db.get(MenuItem, item_id)
    if not mi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
        )
    try_remove_stored_menu_image(mi.image_url)
    iid = mi.id
    db.delete(mi)
    db.commit()
    invalidate_menu_cache(iid)
    return None
