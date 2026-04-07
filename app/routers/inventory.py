from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import (
    Inventory,
    InventoryCategory,
    InventoryLog,
    InventoryLogAction,
    InventoryUnit,
)
from app.schemas.ops import InventoryCreate, StockPatch
from app.utils.responses import err, ok

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _inv_dict(inv: Inventory) -> dict:
    low = inv.current_stock < inv.min_stock_level
    needs = inv.current_stock <= inv.reorder_level
    return {
        "id": inv.id,
        "name": inv.name,
        "sku": inv.sku,
        "category": inv.category.value,
        "unit": inv.unit.value,
        "current_stock": float(inv.current_stock),
        "min_stock_level": float(inv.min_stock_level),
        "reorder_level": float(inv.reorder_level),
        "unit_cost": float(inv.unit_cost),
        "supplier_name": inv.supplier_name,
        "supplier_contact": inv.supplier_contact,
        "is_low_stock": low,
        "needs_reorder": needs,
        "last_restocked_at": inv.last_restocked_at.isoformat().replace("+00:00", "Z")
        if inv.last_restocked_at
        else None,
    }


@router.get("")
def list_inventory(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    category: Annotated[str | None, Query()] = None,
    low_stock: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
):
    q = db.query(Inventory).filter(Inventory.is_active.is_(True))
    if category:
        try:
            q = q.filter(Inventory.category == InventoryCategory(category))
        except ValueError:
            pass
    if low_stock:
        q = q.filter(Inventory.current_stock < Inventory.min_stock_level)
    if search:
        term = f"%{search}%"
        q = q.filter(or_(Inventory.name.like(term), Inventory.sku.like(term)))
    total_items = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    all_active = db.query(Inventory).filter(Inventory.is_active.is_(True))
    low_count = (
        all_active.filter(Inventory.current_stock < Inventory.min_stock_level).count()
    )
    needs_count = all_active.filter(Inventory.current_stock <= Inventory.reorder_level).count()
    total_value = (
        db.query(func.coalesce(func.sum(Inventory.current_stock * Inventory.unit_cost), 0))
        .filter(Inventory.is_active.is_(True))
        .scalar()
    )
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    return ok(
        {
            "items": [_inv_dict(i) for i in rows],
            "summary": {
                "total_items": all_active.count(),
                "low_stock_count": low_count,
                "needs_reorder_count": needs_count,
                "total_value": float(total_value or 0),
            },
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }
    )


@router.get("/{inv_id}")
def get_inventory_item(inv_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Inventory item not found"),
        )
    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.inventory_id == inv_id)
        .order_by(InventoryLog.created_at.desc())
        .limit(50)
        .all()
    )
    data = _inv_dict(inv)
    data["history"] = [
        {
            "id": lg.id,
            "action": lg.action.value,
            "quantity_change": float(lg.quantity_change),
            "previous_stock": float(lg.previous_stock),
            "new_stock": float(lg.new_stock),
            "notes": lg.notes,
            "created_at": lg.created_at.isoformat().replace("+00:00", "Z") if lg.created_at else None,
        }
        for lg in logs
    ]
    return ok(data)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_inventory(body: InventoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    try:
        cat = InventoryCategory(body.category)
        unit = InventoryUnit(body.unit)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid category or unit"),
        ) from None
    inv = Inventory(
        name=body.name,
        sku=body.sku,
        category=cat,
        unit=unit,
        current_stock=body.current_stock,
        min_stock_level=body.min_stock_level,
        reorder_level=body.reorder_level,
        unit_cost=body.unit_cost,
        supplier_name=body.supplier_name,
        supplier_contact=body.supplier_contact,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return ok(_inv_dict(inv))


@router.put("/{inv_id}")
def update_inventory(inv_id: int, body: InventoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Inventory item not found"),
        )
    try:
        inv.category = InventoryCategory(body.category)
        inv.unit = InventoryUnit(body.unit)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid category or unit"),
        ) from None
    inv.name = body.name
    inv.sku = body.sku
    inv.min_stock_level = body.min_stock_level
    inv.reorder_level = body.reorder_level
    inv.unit_cost = body.unit_cost
    inv.supplier_name = body.supplier_name
    inv.supplier_contact = body.supplier_contact
    db.commit()
    db.refresh(inv)
    return ok(_inv_dict(inv))


@router.patch("/{inv_id}/stock")
def adjust_stock(inv_id: int, body: StockPatch, _: CurrentAdmin, db: Session = Depends(get_db)):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Inventory item not found"),
        )
    try:
        act = InventoryLogAction(body.action)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid action"),
        ) from None
    prev = inv.current_stock
    qty = Decimal(str(body.quantity))
    if act == InventoryLogAction.add or act == InventoryLogAction.restock:
        new_stock = prev + qty
    elif act == InventoryLogAction.remove:
        new_stock = prev - qty
    else:
        new_stock = qty
    inv.current_stock = new_stock
    if act == InventoryLogAction.restock or act == InventoryLogAction.add:
        inv.last_restocked_at = datetime.now(timezone.utc)
    log = InventoryLog(
        inventory_id=inv.id,
        action=act,
        quantity_change=qty if act != InventoryLogAction.adjust else new_stock - prev,
        previous_stock=prev,
        new_stock=new_stock,
        notes=body.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(inv)
    return ok(_inv_dict(inv))


@router.get("/{inv_id}/logs")
def inventory_logs(inv_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    if not db.get(Inventory, inv_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Inventory item not found"),
        )
    logs = (
        db.query(InventoryLog)
        .filter(InventoryLog.inventory_id == inv_id)
        .order_by(InventoryLog.created_at.desc())
        .all()
    )
    return ok(
        [
            {
                "id": lg.id,
                "action": lg.action.value,
                "quantity_change": float(lg.quantity_change),
                "previous_stock": float(lg.previous_stock),
                "new_stock": float(lg.new_stock),
                "notes": lg.notes,
                "created_at": lg.created_at.isoformat().replace("+00:00", "Z") if lg.created_at else None,
            }
            for lg in logs
        ]
    )


@router.delete("/{inv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory(inv_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    inv = db.get(Inventory, inv_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Inventory item not found"),
        )
    inv.is_active = False
    db.commit()
    return None
