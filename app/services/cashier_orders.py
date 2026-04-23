"""Cashier POS order workflows: atomic writes, server-side totals, payment, and holds."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.deps import CashierPrincipal
from app.models import (
    Customer,
    Order,
    OrderItem,
    OrderItemTopping,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    StoreSetting,
)
from app.schemas.cashier import (
    CashierCancelBody,
    CashierItemQuantityBody,
    CashierOrderCreate,
    CashierOrderItemAdd,
    CashierPayBody,
)
from app.services import order_ops
from app.utils.responses import err


def _terminal_statuses() -> set:
    return {
        OrderStatus.completed,
        OrderStatus.cancelled,
        OrderStatus.delivered,
    }


def _ensure_editable(order: Order) -> None:
    if order.payment_status == PaymentStatus.paid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err("ORDER_LOCKED", "This order is paid and cannot be edited"),
        )
    if order.status in _terminal_statuses():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err("ORDER_NOT_EDITABLE", "This order can no longer be edited"),
        )


def _load_order_for_edit(db: Session, order_id: int) -> Order:
    o = (
        db.query(Order)
        .options(joinedload(Order.items).joinedload(OrderItem.toppings))
        .filter(Order.id == order_id)
        .first()
    )
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    _ensure_editable(o)
    return o


def parse_payment_method(raw: str) -> PaymentMethod:
    key = (raw or "").strip().lower()
    if key == "upi":
        return PaymentMethod.online
    try:
        return PaymentMethod(key)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid payment_method"),
        ) from None


def create_order(
    db: Session,
    principal: CashierPrincipal,
    body: CashierOrderCreate,
) -> Order:
    try:
        ot = OrderType(body.order_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid order_type"),
        ) from None
    pm = parse_payment_method(body.payment_method)

    subtotal, line_entities = order_ops.build_order_line_entities(db, body.items)
    discount_amount = Decimal("0")
    tax_amount, delivery_fee, total_amount = order_ops.compute_totals(
        db, subtotal=subtotal, order_type=ot, discount_amount=discount_amount
    )

    cust_id = body.customer_id
    cname = body.customer_name
    cphone = body.customer_phone
    cemail = body.customer_email
    if cust_id:
        cu = db.get(Customer, cust_id)
        if cu:
            cname = f"{cu.first_name} {cu.last_name}"
            cphone = cu.phone
            cemail = cu.email

    try:
        order = Order(
            order_number=order_ops.next_order_number(db),
            customer_id=cust_id,
            customer_name=cname,
            customer_phone=cphone,
            customer_email=cemail,
            order_type=ot,
            status=OrderStatus.pending,
            table_number=body.table_number,
            delivery_address=body.delivery_address,
            delivery_instructions=body.delivery_instructions,
            subtotal=subtotal,
            tax_amount=tax_amount,
            delivery_fee=delivery_fee,
            discount_amount=discount_amount,
            discount_code=body.discount_code,
            total_amount=total_amount,
            payment_method=pm,
            payment_status=PaymentStatus.pending,
            notes=body.notes,
            assigned_employee_id=principal.employee.id,
        )
        db.add(order)
        db.flush()
        for oi, tops in line_entities:
            oi.order_id = order.id
            db.add(oi)
            db.flush()
            for t in tops:
                t.order_item_id = oi.id
                db.add(t)

        if cust_id:
            cu = db.get(Customer, cust_id)
            if cu:
                cu.total_orders = (cu.total_orders or 0) + 1
                cu.total_spent = (cu.total_spent or Decimal("0")) + total_amount

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(order)
    return (
        db.query(Order)
        .options(joinedload(Order.items).joinedload(OrderItem.toppings))
        .filter(Order.id == order.id)
        .first()
        or order
    )


def add_line_item(db: Session, order_id: int, body: CashierOrderItemAdd) -> Order:
    order = _load_order_for_edit(db, order_id)
    _, new_lines = order_ops.build_order_line_entities(db, [body.item])
    if not new_lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "No line item to add"),
        )
    oi, tops = new_lines[0]
    oi.order_id = order.id
    db.add(oi)
    db.flush()
    for t in tops:
        t.order_item_id = oi.id
        db.add(t)
    order_ops.refresh_order_totals_from_items(db, order)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _load_order_for_edit(db, order_id)


def update_line_quantity(db: Session, order_id: int, item_id: int, body: CashierItemQuantityBody) -> Order:
    order = _load_order_for_edit(db, order_id)
    oi = db.get(OrderItem, item_id)
    if not oi or oi.order_id != order.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order line not found"),
        )
    oi.quantity = body.quantity
    order_ops.recompute_line_total(oi)
    order_ops.refresh_order_totals_from_items(db, order)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _load_order_for_edit(db, order_id)


def remove_line_item(db: Session, order_id: int, item_id: int) -> Order:
    order = _load_order_for_edit(db, order_id)
    oi = db.get(OrderItem, item_id)
    if not oi or oi.order_id != order.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order line not found"),
        )
    db.delete(oi)
    db.flush()
    order_ops.refresh_order_totals_from_items(db, order)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _load_order_for_edit(db, order_id)


def list_active_orders(db: Session) -> list[Order]:
    return (
        db.query(Order)
        .filter(Order.status.in_([OrderStatus.pending, OrderStatus.preparing]))
        .order_by(Order.created_at.desc())
        .all()
    )


def get_order(db: Session, order_id: int) -> Order:
    o = (
        db.query(Order)
        .options(joinedload(Order.items).joinedload(OrderItem.toppings))
        .filter(Order.id == order_id)
        .first()
    )
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    return o


def process_payment(db: Session, order_id: int, body: CashierPayBody) -> dict:
    order = get_order(db, order_id)
    if order.status == OrderStatus.cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err("ORDER_CANCELLED", "Cannot pay a cancelled order"),
        )
    if order.payment_status == PaymentStatus.paid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err("ORDER_ALREADY_PAID", "Order is already paid"),
        )
    pm = parse_payment_method(body.payment_method)
    change = Decimal("0")
    if pm == PaymentMethod.cash:
        if body.amount_received is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("VALIDATION_ERROR", "amount_received is required for cash payments"),
            )
        if body.amount_received < order.total_amount:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("INSUFFICIENT_AMOUNT", "amount_received is less than order total"),
            )
        change = body.amount_received - order.total_amount

    order.payment_method = pm
    order.payment_status = PaymentStatus.paid
    order.status = OrderStatus.confirmed
    order.paid_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return {
        "order": order_ops.order_detail_dict(db, order),
        "change": float(change) if pm == PaymentMethod.cash else None,
    }


def cancel_order(db: Session, order_id: int, body: CashierCancelBody) -> Order:
    order = get_order(db, order_id)
    if order.status == OrderStatus.cancelled:
        return order
    if order.payment_status == PaymentStatus.paid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err("ORDER_LOCKED", "Paid orders cannot be cancelled here"),
        )
    order.status = OrderStatus.cancelled
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancellation_reason = body.reason
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return order


def hold_order(db: Session, order_id: int) -> Order:
    order = _load_order_for_edit(db, order_id)
    order.status = OrderStatus.on_hold
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return get_order(db, order_id)


def invoice_json(db: Session, order_id: int) -> dict:
    o = get_order(db, order_id)
    store = db.query(StoreSetting).first()
    store_block = None
    if store:
        store_block = {
            "store_name": store.store_name,
            "address": " ".join(
                x for x in [store.address_line1, store.city, store.state, store.postal_code] if x
            ),
            "phone": store.phone,
            "tax_id": None,
        }
    detail = order_ops.order_detail_dict(db, o)
    return {"issued_at": datetime.now(timezone.utc).isoformat(), "store": store_block, "order": detail}


def receipt_json(db: Session, order_id: int) -> dict:
    inv = invoice_json(db, order_id)
    o = inv["order"]
    lines = []
    for it in o.get("items") or []:
        lines.append(
            {
                "name": it.get("name"),
                "qty": it.get("quantity"),
                "unit": it.get("unit_price"),
                "total": it.get("total_price"),
            }
        )
    return {
        "order_number": o.get("order_number"),
        "items": lines,
        "subtotal": o.get("subtotal"),
        "tax": o.get("tax_amount"),
        "delivery_fee": o.get("delivery_fee"),
        "total": o.get("total_amount"),
        "payment": {"method": o.get("payment_method"), "status": o.get("payment_status")},
    }
