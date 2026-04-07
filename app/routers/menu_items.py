from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Category, MenuItem, MenuItemSize, SizeName, Subcategory
from app.schemas.menu import AvailabilityPatch, MenuItemCreate, MenuItemUpdate
from app.utils.responses import err, ok
from app.utils.slug import slugify

router = APIRouter(prefix="/menu-items", tags=["menu-items"])


def _item_dict(db: Session, mi: MenuItem) -> dict:
    cat = db.get(Category, mi.category_id)
    sub = db.get(Subcategory, mi.subcategory_id) if mi.subcategory_id else None
    sizes = [
        {
            "size": s.size_name.value,
            "price": float(s.price),
            "is_default": s.is_default,
        }
        for s in sorted(mi.sizes, key=lambda x: x.size_name.value)
    ]
    return {
        "id": mi.id,
        "name": mi.name,
        "slug": mi.slug,
        "description": mi.description,
        "category": {
            "id": cat.id if cat else mi.category_id,
            "name": cat.name if cat else "",
            "has_sizes": cat.has_sizes if cat else False,
        },
        "subcategory": (
            {"id": sub.id, "name": sub.name} if sub else None
        ),
        "base_price": float(mi.base_price),
        "sizes": sizes,
        "image_url": mi.image_url,
        "is_available": mi.is_available,
        "is_featured": mi.is_featured,
        "preparation_time_minutes": mi.preparation_time_minutes,
        "calories": mi.calories,
        "allergens": mi.allergens,
    }


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
    rows = (
        q.order_by(MenuItem.display_order, MenuItem.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_menu_item(body: MenuItemCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
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
        image_url=body.image_url,
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
    db.refresh(mi)
    return ok(_item_dict(db, mi))


@router.put("/{item_id}")
def update_menu_item(item_id: int, body: MenuItemUpdate, _: CurrentAdmin, db: Session = Depends(get_db)):
    mi = db.get(MenuItem, item_id)
    if not mi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
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
    if body.image_url is not None:
        mi.image_url = body.image_url
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
    db.commit()
    db.refresh(mi)
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
    return ok(_item_dict(db, mi))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_item(item_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    mi = db.get(MenuItem, item_id)
    if not mi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Menu item not found"),
        )
    db.delete(mi)
    db.commit()
    return None
