from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.cache import cache_delete, cache_get_json, cache_set_json
from app.models import Category, MenuItem
from app.services.menu_payloads import menu_item_to_dict


def categories_payload(db: Session) -> list[dict]:
    key = "cashier:categories:v1"
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    rows = db.query(Category).order_by(Category.display_order, Category.id).all()
    out = [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "description": c.description,
            "has_sizes": c.has_sizes,
            "display_order": c.display_order,
            "is_active": c.is_active,
            "subcategories": [
                {
                    "id": s.id,
                    "name": s.name,
                    "slug": s.slug,
                    "display_order": s.display_order,
                    "is_active": s.is_active,
                }
                for s in sorted(c.subcategories, key=lambda x: (x.display_order, x.id))
            ],
        }
        for c in rows
    ]
    cache_set_json(key, out, settings.cashier_menu_cache_ttl_seconds)
    return out


def menu_list_payload(db: Session, *, only_available: bool = True) -> list[dict]:
    key = f"cashier:menu:list:v1:{'avail' if only_available else 'all'}"
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    q = db.query(MenuItem).options(joinedload(MenuItem.sizes))
    if only_available:
        q = q.filter(MenuItem.is_available.is_(True))
    rows = q.order_by(MenuItem.display_order, MenuItem.id).all()
    out = [menu_item_to_dict(db, mi) for mi in rows]
    cache_set_json(key, out, settings.cashier_menu_cache_ttl_seconds)
    return out


def menu_item_payload(db: Session, item_id: int) -> dict | None:
    key = f"cashier:menu:item:v1:{item_id}"
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    mi = db.query(MenuItem).options(joinedload(MenuItem.sizes)).filter(MenuItem.id == item_id).first()
    if not mi:
        return None
    out = menu_item_to_dict(db, mi)
    cache_set_json(key, out, settings.cashier_menu_cache_ttl_seconds)
    return out


def invalidate_menu_cache(menu_item_id: int | None = None) -> None:
    """Call from admin menu mutations if cashier cache should clear immediately."""
    cache_delete("cashier:categories:v1")
    cache_delete("cashier:menu:list:v1:avail")
    cache_delete("cashier:menu:list:v1:all")
    if menu_item_id is not None:
        cache_delete(f"cashier:menu:item:v1:{menu_item_id}")
