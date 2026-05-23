"""Category array helpers for toppings and crusts APIs."""

from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import exists, or_
from sqlalchemy.orm import Query, Session

from app.models import Category, Crust, CrustCategory, Topping, ToppingCategory
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


def topping_category_ids(db: Session, topping: Topping) -> list[int]:
    rows = (
        db.query(ToppingCategory.category_id)
        .filter(ToppingCategory.topping_id == topping.id)
        .order_by(ToppingCategory.category_id)
        .all()
    )
    if rows:
        return [r[0] for r in rows]
    return [topping.category_id] if topping.category_id else []


def crust_category_ids(db: Session, crust: Crust) -> list[int]:
    rows = (
        db.query(CrustCategory.category_id)
        .filter(CrustCategory.crust_id == crust.id)
        .order_by(CrustCategory.category_id)
        .all()
    )
    if rows:
        return [r[0] for r in rows]
    return [crust.category_id] if crust.category_id else []


def _sync_topping_category_links(db: Session, topping: Topping, category_ids: list[int]) -> None:
    if topping.id is None:
        db.flush()
    db.query(ToppingCategory).filter(ToppingCategory.topping_id == topping.id).delete(
        synchronize_session=False
    )
    for cid in category_ids:
        db.add(ToppingCategory(topping_id=topping.id, category_id=cid))


def _sync_crust_category_links(db: Session, crust: Crust, category_ids: list[int]) -> None:
    if crust.id is None:
        db.flush()
    db.query(CrustCategory).filter(CrustCategory.crust_id == crust.id).delete(
        synchronize_session=False
    )
    for cid in category_ids:
        db.add(CrustCategory(crust_id=crust.id, category_id=cid))


def assign_topping_categories(db: Session, topping: Topping, category_ids: list[int]) -> None:
    cats = load_categories_for_ids(db, category_ids)
    topping.category_id = cats[0].id
    _sync_topping_category_links(db, topping, [c.id for c in cats])


def assign_crust_categories(db: Session, crust: Crust, category_ids: list[int]) -> None:
    if not category_ids:
        crust.category_id = None
        if crust.id is not None:
            db.query(CrustCategory).filter(CrustCategory.crust_id == crust.id).delete(
                synchronize_session=False
            )
        return
    cats = load_categories_for_ids(db, category_ids)
    crust.category_id = cats[0].id
    _sync_crust_category_links(db, crust, [c.id for c in cats])


def filter_toppings_by_category(q: Query, category_id: int) -> Query:
    link_exists = exists().where(
        (ToppingCategory.topping_id == Topping.id)
        & (ToppingCategory.category_id == category_id)
    )
    return q.filter(or_(Topping.category_id == category_id, link_exists))


def filter_crusts_by_category(q: Query, category_id: int) -> Query:
    link_exists = exists().where(
        (CrustCategory.crust_id == Crust.id) & (CrustCategory.category_id == category_id)
    )
    global_crust = ~exists().where(CrustCategory.crust_id == Crust.id) & (Crust.category_id.is_(None))
    return q.filter(or_(Crust.category_id == category_id, link_exists, global_crust))


def topping_item_dict(db: Session, topping: Topping) -> dict:
    cat_ids = topping_category_ids(db, topping)
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


def crust_item_dict(db: Session, crust: Crust) -> dict:
    cat_ids = crust_category_ids(db, crust)
    cats = load_categories_for_ids(db, cat_ids) if cat_ids else []
    return {
        "id": crust.id,
        "name": crust.name,
        "category_ids": cat_ids,
        "categories": categories_payload(cats),
        "price": float(crust.price),
        "is_available": crust.is_available,
        "sort_order": crust.sort_order,
    }


def list_topping_items(db: Session, toppings: list[Topping]) -> list[dict]:
    """One entry per topping (for admin list; no repeat per category)."""
    return [topping_item_dict(db, t) for t in toppings]


def list_crust_items(db: Session, crusts: list[Crust]) -> list[dict]:
    """One entry per crust (for admin list; no repeat per category)."""
    return [crust_item_dict(db, c) for c in crusts]


def group_toppings_by_category(db: Session, toppings: list[Topping]) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    meta: dict[int, Category] = {}
    uncategorized: list[dict] = []

    for t in toppings:
        item = topping_item_dict(db, t)
        cat_ids = topping_category_ids(db, t)
        if not cat_ids:
            uncategorized.append(item)
            continue
        for cid in cat_ids:
            buckets[cid].append(item)
            if cid not in meta:
                cat = db.get(Category, cid)
                if cat:
                    meta[cid] = cat

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


def group_crusts_by_category(db: Session, crusts: list[Crust]) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    meta: dict[int, Category] = {}
    uncategorized: list[dict] = []

    for c in crusts:
        item = crust_item_dict(db, c)
        cat_ids = crust_category_ids(db, c)
        if not cat_ids:
            uncategorized.append(item)
            continue
        for cid in cat_ids:
            buckets[cid].append(item)
            if cid not in meta:
                cat = db.get(Category, cid)
                if cat:
                    meta[cid] = cat

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


def detach_category_from_toppings_and_crusts(db: Session, category_id: int) -> None:
    """Remove category links; delete toppings with no categories left."""
    db.query(ToppingCategory).filter(ToppingCategory.category_id == category_id).delete(
        synchronize_session=False
    )
    db.query(CrustCategory).filter(CrustCategory.category_id == category_id).delete(
        synchronize_session=False
    )

    linked_topping_ids = {
        row[0]
        for row in db.query(ToppingCategory.topping_id).distinct().all()
    }
    for t in db.query(Topping).filter(Topping.category_id == category_id).all():
        if t.id not in linked_topping_ids:
            db.delete(t)
        else:
            remaining = topping_category_ids(db, t)
            t.category_id = remaining[0]

    for c in db.query(Crust).filter(Crust.category_id == category_id).all():
        remaining = crust_category_ids(db, c)
        c.category_id = remaining[0] if remaining else None
