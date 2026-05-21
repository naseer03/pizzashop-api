"""Category array helpers for toppings and crusts APIs."""

from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Category, Crust, Topping
from app.utils.responses import err


def load_categories_for_ids(db: Session, category_ids: list[int]) -> list[Category]:
    if not category_ids:
        return []
    rows = db.query(Category).filter(Category.id.in_(category_ids)).all()
    by_id = {c.id: c for c in rows}
    missing = [cid for cid in category_ids if cid not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err(
                "VALIDATION_ERROR",
                "Invalid category id(s) in category_ids",
                details={"missing_category_ids": missing},
            ),
        )
    return [by_id[cid] for cid in category_ids]


def categories_payload(categories: list[Category]) -> list[dict]:
    return [{"id": c.id, "name": c.name} for c in categories]


def categories_payload_for_crust(crust: Crust) -> list[dict]:
    if not crust.category_id:
        return []
    cat = crust.category
    if cat is None:
        return [{"id": crust.category_id, "name": ""}]
    return categories_payload([cat])


def assign_topping_categories(db: Session, topping: Topping, category_ids: list[int]) -> None:
    cats = load_categories_for_ids(db, category_ids)
    topping.category_id = cats[0].id


def assign_crust_categories(db: Session, crust: Crust, category_ids: list[int]) -> None:
    if not category_ids:
        crust.category_id = None
        return
    cats = load_categories_for_ids(db, category_ids)
    crust.category_id = cats[0].id


def topping_item_dict(db: Session, topping: Topping) -> dict:
    cat_ids = [topping.category_id]
    cats = load_categories_for_ids(db, cat_ids)
    return {
        "id": topping.id,
        "name": topping.name,
        "category_ids": cat_ids,
        "categories": categories_payload(cats),
        "price": float(topping.price),
        "is_available": topping.is_available,
        "sort_order": topping.sort_order,
    }


def crust_item_dict(crust: Crust) -> dict:
    cat_ids = [crust.category_id] if crust.category_id else []
    return {
        "id": crust.id,
        "name": crust.name,
        "category_ids": cat_ids,
        "categories": categories_payload_for_crust(crust),
        "price": float(crust.price),
        "is_available": crust.is_available,
        "sort_order": crust.sort_order,
    }


def group_toppings_by_category(db: Session, toppings: list[Topping]) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    meta: dict[int, Category] = {}
    uncategorized: list[dict] = []

    for t in toppings:
        item = topping_item_dict(db, t)
        if t.category_id:
            buckets[t.category_id].append(item)
            if t.category_id not in meta:
                cat = db.get(Category, t.category_id)
                if cat:
                    meta[t.category_id] = cat
        else:
            uncategorized.append(item)

    out = [
        {
            "id": meta[cid].id,
            "name": meta[cid].name,
            "toppings": buckets[cid],
        }
        for cid in sorted(meta.keys(), key=lambda i: (meta[i].display_order, meta[i].id))
    ]
    if uncategorized:
        out.append({"id": None, "name": "Uncategorized", "toppings": uncategorized})
    return out


def group_crusts_by_category(crusts: list[Crust]) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    meta: dict[int, Category] = {}
    uncategorized: list[dict] = []

    for c in crusts:
        item = crust_item_dict(c)
        if c.category_id:
            buckets[c.category_id].append(item)
            if c.category_id not in meta and c.category:
                meta[c.category_id] = c.category
        else:
            uncategorized.append(item)

    out = [
        {
            "id": meta[cid].id,
            "name": meta[cid].name,
            "crusts": buckets[cid],
        }
        for cid in sorted(meta.keys(), key=lambda i: (meta[i].display_order, meta[i].id))
    ]
    if uncategorized:
        out.append({"id": None, "name": "Uncategorized", "crusts": uncategorized})
    return out
