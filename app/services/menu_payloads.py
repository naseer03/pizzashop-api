from sqlalchemy.orm import Session

from app.models import Category, MenuItem, Subcategory


def menu_item_to_dict(db: Session, mi: MenuItem) -> dict:
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
        "subcategory": ({"id": sub.id, "name": sub.name} if sub else None),
        "base_price": float(mi.base_price),
        "sizes": sizes,
        "image_url": mi.image_url,
        "is_available": mi.is_available,
        "is_featured": mi.is_featured,
        "preparation_time_minutes": mi.preparation_time_minutes,
        "calories": mi.calories,
        "allergens": mi.allergens,
    }
