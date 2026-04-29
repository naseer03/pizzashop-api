"""Shared order construction, pricing, and serialization used by admin and cashier routes."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Crust,
    Customer,
    Employee,
    MenuItem,
    MenuItemSize,
    Order,
    OrderItem,
    OrderItemTopping,
    OrderType,
    SizeName,
    StoreSetting,
    Topping,
)
from app.schemas.orders import OrderItemIn
from app.utils.responses import err


def parse_order_type(raw: str) -> OrderType:
    key = (raw or "").strip().lower()
    try:
        return OrderType(key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid order_type"),
        ) from None


def parse_order_status(raw: str | None) -> OrderStatus:
    key = (raw or "").strip().lower()
    if not key:
        return OrderStatus.pending
    # Compatibility with external payloads that send CREATED.
    if key == "created":
        return OrderStatus.pending
    try:
        return OrderStatus(key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid status"),
        ) from None


def parse_payment_status(raw: str | None) -> PaymentStatus:
    key = (raw or "").strip().lower()
    if not key:
        return PaymentStatus.pending
    try:
        return PaymentStatus(key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid payment_status"),
        ) from None


def next_order_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"ORD-{year}-"
    last = (
        db.query(Order.order_number)
        .filter(Order.order_number.like(f"{prefix}%"))
        .order_by(Order.id.desc())
        .first()
    )
    n = 1
    if last and last[0]:
        try:
            n = int(last[0].split("-")[-1]) + 1
        except ValueError:
            n = 1
    return f"{prefix}{n:03d}"


def size_enum(s: str | None) -> SizeName | None:
    if not s:
        return None
    try:
        return SizeName(s)
    except ValueError:
        return None


def order_detail_dict(db: Session, o: Order) -> dict:
    cust = None
    if o.customer_id:
        c = db.get(Customer, o.customer_id)
        if c:
            cust = {
                "id": c.id,
                "name": f"{c.first_name} {c.last_name}",
                "phone": c.phone,
                "email": c.email,
            }
    items_out = []
    for li in o.items:
        crust_obj = None
        if li.crust_id:
            crust_obj = {
                "id": li.crust_id,
                "name": li.crust_name or "",
                "price": float(li.crust_price),
            }
        tops = [
            {"id": t.topping_id, "name": t.topping_name, "price": float(t.topping_price)}
            for t in li.toppings
        ]
        items_out.append(
            {
                "id": li.id,
                "menu_item_id": li.menu_item_id,
                "name": li.menu_item_name,
                "size": li.size.value if li.size else None,
                "crust": crust_obj,
                "toppings": tops,
                "quantity": li.quantity,
                "unit_price": float(li.unit_price),
                "toppings_price": float(li.toppings_price),
                "total_price": float(li.total_price),
                "special_instructions": li.special_instructions,
            }
        )
    emp = None
    if o.assigned_employee_id:
        e = db.get(Employee, o.assigned_employee_id)
        if e:
            emp = {"id": e.id, "name": f"{e.first_name} {e.last_name}"}
    return {
        "id": o.id,
        "order_number": o.order_number,
        "customer": cust,
        "order_type": o.order_type.value,
        "status": o.status.value,
        "table_number": o.table_number,
        "delivery_address": o.delivery_address,
        "delivery_instructions": o.delivery_instructions,
        "items": items_out,
        "subtotal": float(o.subtotal),
        "tax_amount": float(o.tax_amount),
        "delivery_fee": float(o.delivery_fee),
        "discount_amount": float(o.discount_amount),
        "discount_code": o.discount_code,
        "total_amount": float(o.total_amount),
        "payment_method": o.payment_method.value,
        "payment_status": o.payment_status.value,
        "kot_printed": o.kot_printed,
        "paid_at": o.paid_at.isoformat().replace("+00:00", "Z") if o.paid_at else None,
        "notes": o.notes,
        "assigned_employee": emp,
        "estimated_ready_time": o.estimated_ready_time.isoformat().replace("+00:00", "Z")
        if o.estimated_ready_time
        else None,
        "created_at": o.created_at.isoformat().replace("+00:00", "Z") if o.created_at else None,
        "updated_at": o.updated_at.isoformat().replace("+00:00", "Z") if o.updated_at else None,
    }


def _store_defaults(db: Session) -> tuple[Decimal, Decimal, Decimal]:
    store = db.query(StoreSetting).first()
    tax_rate = store.tax_rate if store else Decimal("8.00")
    base_delivery = store.delivery_fee if store else Decimal("3.99")
    free_delivery_min = store.free_delivery_minimum_order if store else Decimal("0")
    return tax_rate, base_delivery, free_delivery_min


def compute_totals(
    db: Session,
    *,
    subtotal: Decimal,
    order_type: OrderType,
    discount_amount: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal, Decimal]:
    tax_rate, base_delivery, free_delivery_min = _store_defaults(db)
    if order_type == OrderType.delivery:
        waive = free_delivery_min > 0 and subtotal >= free_delivery_min
        delivery_fee = Decimal("0") if waive else base_delivery
    else:
        delivery_fee = Decimal("0")
    tax_amount = (subtotal - discount_amount) * (tax_rate / Decimal("100"))
    total_amount = subtotal + tax_amount + delivery_fee - discount_amount
    return tax_amount, delivery_fee, total_amount


def build_order_line_entities(
    db: Session, items: list[OrderItemIn]
) -> tuple[Decimal, list[tuple[OrderItem, list[OrderItemTopping]]]]:
    subtotal = Decimal("0")
    line_entities: list[tuple[OrderItem, list[OrderItemTopping]]] = []

    for it in items:
        mi = db.get(MenuItem, it.menu_item_id)
        if not mi:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("VALIDATION_ERROR", f"Menu item {it.menu_item_id} not found"),
            )
        if not mi.is_available:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("MENU_ITEM_UNAVAILABLE", f"Menu item {it.menu_item_id} is not available"),
            )
        size_e = size_enum(it.size)
        unit_price = mi.base_price
        if size_e:
            sz = (
                db.query(MenuItemSize)
                .filter(MenuItemSize.menu_item_id == mi.id, MenuItemSize.size_name == size_e)
                .first()
            )
            if sz:
                unit_price = sz.price
        crust_price = Decimal("0")
        crust_name = None
        crust_id = it.crust_id
        if crust_id:
            cr = db.get(Crust, crust_id)
            if cr:
                if not cr.is_available:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=err("CRUST_UNAVAILABLE", f"Crust {crust_id} is not available"),
                    )
                crust_price = cr.price
                crust_name = cr.name
        toppings_total = Decimal("0")
        top_rows: list[OrderItemTopping] = []
        for tp in it.toppings:
            top = db.get(Topping, tp.topping_id)
            if not top:
                continue
            if not top.is_available:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=err("TOPPING_UNAVAILABLE", f"Topping {tp.topping_id} is not available"),
                )
            qty = max(1, tp.quantity)
            line_tp = top.price * qty
            toppings_total += line_tp
            top_rows.append(
                OrderItemTopping(
                    topping_id=top.id,
                    topping_name=top.name,
                    topping_price=top.price,
                    quantity=qty,
                )
            )
        if it.quantity < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("VALIDATION_ERROR", "Quantity must be at least 1"),
            )
        line_total = (unit_price + crust_price + toppings_total) * it.quantity
        subtotal += line_total
        oi = OrderItem(
            menu_item_id=mi.id,
            menu_item_name=mi.name,
            size=size_e,
            crust_id=crust_id,
            crust_name=crust_name,
            crust_price=crust_price,
            quantity=it.quantity,
            unit_price=unit_price,
            toppings_price=toppings_total,
            total_price=line_total,
            special_instructions=it.special_instructions,
        )
        line_entities.append((oi, top_rows))

    return subtotal, line_entities


def recompute_line_total(oi: OrderItem) -> None:
    per_unit = oi.unit_price + oi.crust_price + oi.toppings_price
    oi.total_price = per_unit * oi.quantity


def refresh_order_totals_from_items(db: Session, order: Order) -> None:
    rows = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    subtotal = sum((r.total_price for r in rows), Decimal("0"))
    order.subtotal = subtotal
    discount = order.discount_amount or Decimal("0")
    tax_amount, delivery_fee, total_amount = compute_totals(
        db, subtotal=subtotal, order_type=order.order_type, discount_amount=discount
    )
    order.tax_amount = tax_amount
    order.delivery_fee = delivery_fee
    order.total_amount = total_amount
