from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import (
    Crust,
    Customer,
    Employee,
    MenuItem,
    MenuItemSize,
    Order,
    OrderItem,
    OrderItemTopping,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    SizeName,
    StoreSetting,
    Topping,
)
from app.schemas.orders import (
    OrderAssignPatch,
    OrderCancelBody,
    OrderCreate,
    OrderStatusPatch,
    OrderUpdate,
)
from app.utils.responses import err, ok

router = APIRouter(prefix="/orders", tags=["orders"])


def _size_enum(s: str | None) -> SizeName | None:
    if not s:
        return None
    try:
        return SizeName(s)
    except ValueError:
        return None


def _next_order_number(db: Session) -> str:
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


@router.get("")
def list_orders(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    order_type: Annotated[str | None, Query()] = None,
    payment_status: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_order: Annotated[str, Query()] = "desc",
):
    q = db.query(Order)
    if status_filter:
        try:
            q = q.filter(Order.status == OrderStatus(status_filter))
        except ValueError:
            pass
    if order_type:
        try:
            q = q.filter(Order.order_type == OrderType(order_type))
        except ValueError:
            pass
    if payment_status:
        try:
            q = q.filter(Order.payment_status == PaymentStatus(payment_status))
        except ValueError:
            pass
    if date_from:
        q = q.filter(func.date(Order.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(Order.created_at) <= date_to)
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Order.order_number.like(term),
                Order.customer_name.like(term),
                Order.customer_phone.like(term),
            )
        )
    total_items = q.count()
    col = Order.created_at if sort_by != "total_amount" else Order.total_amount
    if sort_order == "asc":
        q = q.order_by(col.asc())
    else:
        q = q.order_by(col.desc())
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    orders_out = []
    for o in rows:
        items_count = (
            db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
            .filter(OrderItem.order_id == o.id)
            .scalar()
        )
        orders_out.append(
            {
                "id": o.id,
                "order_number": o.order_number,
                "customer_name": o.customer_name,
                "customer_phone": o.customer_phone,
                "order_type": o.order_type.value,
                "status": o.status.value,
                "items_count": int(items_count or 0),
                "subtotal": float(o.subtotal),
                "tax_amount": float(o.tax_amount),
                "delivery_fee": float(o.delivery_fee),
                "discount_amount": float(o.discount_amount),
                "total_amount": float(o.total_amount),
                "payment_method": o.payment_method.value,
                "payment_status": o.payment_status.value,
                "created_at": o.created_at.isoformat().replace("+00:00", "Z") if o.created_at else None,
                "estimated_ready_time": o.estimated_ready_time.isoformat().replace("+00:00", "Z")
                if o.estimated_ready_time
                else None,
            }
        )
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    return ok(
        {
            "orders": orders_out,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }
    )


def _order_detail_dict(db: Session, o: Order) -> dict:
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
        "paid_at": o.paid_at.isoformat().replace("+00:00", "Z") if o.paid_at else None,
        "notes": o.notes,
        "assigned_employee": emp,
        "estimated_ready_time": o.estimated_ready_time.isoformat().replace("+00:00", "Z")
        if o.estimated_ready_time
        else None,
        "created_at": o.created_at.isoformat().replace("+00:00", "Z") if o.created_at else None,
        "updated_at": o.updated_at.isoformat().replace("+00:00", "Z") if o.updated_at else None,
    }


@router.get("/{order_id}")
def get_order(order_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    o = (
        db.query(Order)
        .options(
            joinedload(Order.items).joinedload(OrderItem.toppings),
        )
        .filter(Order.id == order_id)
        .first()
    )
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    return ok(_order_detail_dict(db, o))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    try:
        ot = OrderType(body.order_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid order_type"),
        ) from None
    try:
        pm = PaymentMethod(body.payment_method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid payment_method"),
        ) from None

    store = db.query(StoreSetting).first()
    tax_rate = store.tax_rate if store else Decimal("8.00")
    delivery_fee = Decimal("3.99") if ot == OrderType.delivery else Decimal("0")

    subtotal = Decimal("0")
    line_entities: list[tuple[OrderItem, list[OrderItemTopping]]] = []

    for it in body.items:
        mi = db.get(MenuItem, it.menu_item_id)
        if not mi:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("VALIDATION_ERROR", f"Menu item {it.menu_item_id} not found"),
            )
        size_e = _size_enum(it.size)
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
                crust_price = cr.price
                crust_name = cr.name
        toppings_total = Decimal("0")
        top_rows: list[OrderItemTopping] = []
        for tp in it.toppings:
            top = db.get(Topping, tp.topping_id)
            if not top:
                continue
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

    discount_amount = Decimal("0")
    tax_amount = (subtotal - discount_amount) * (tax_rate / Decimal("100"))
    total_amount = subtotal + tax_amount + delivery_fee - discount_amount

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

    order = Order(
        order_number=_next_order_number(db),
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
    db.refresh(order)
    return ok(
        {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status.value,
            "total_amount": float(order.total_amount),
            "created_at": order.created_at.isoformat().replace("+00:00", "Z") if order.created_at else None,
        }
    )


@router.put("/{order_id}")
def update_order(order_id: int, body: OrderUpdate, _: CurrentAdmin, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    if body.customer_name is not None:
        o.customer_name = body.customer_name
    if body.customer_phone is not None:
        o.customer_phone = body.customer_phone
    if body.customer_email is not None:
        o.customer_email = body.customer_email
    if body.table_number is not None:
        o.table_number = body.table_number
    if body.delivery_address is not None:
        o.delivery_address = body.delivery_address
    if body.delivery_instructions is not None:
        o.delivery_instructions = body.delivery_instructions
    if body.notes is not None:
        o.notes = body.notes
    db.commit()
    db.refresh(o)
    return ok(_order_detail_dict(db, o))


@router.patch("/{order_id}/status")
def patch_status(order_id: int, body: OrderStatusPatch, _: CurrentAdmin, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    try:
        o.status = OrderStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", "Invalid status"),
        ) from None
    if body.estimated_ready_time:
        o.estimated_ready_time = datetime.fromisoformat(
            body.estimated_ready_time.replace("Z", "+00:00")
        )
    db.commit()
    db.refresh(o)
    return ok(_order_detail_dict(db, o))


@router.patch("/{order_id}/assign")
def assign_order(order_id: int, body: OrderAssignPatch, _: CurrentAdmin, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    if not db.get(Employee, body.employee_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("RESOURCE_NOT_FOUND", "Employee not found"),
        )
    o.assigned_employee_id = body.employee_id
    db.commit()
    db.refresh(o)
    return ok(_order_detail_dict(db, o))


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, body: OrderCancelBody, _: CurrentAdmin, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    o.status = OrderStatus.cancelled
    o.cancelled_at = datetime.now(timezone.utc)
    o.cancellation_reason = body.reason
    db.commit()
    return ok({"id": o.id, "status": o.status.value})


@router.post("/{order_id}/refund")
def refund_order(order_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Order not found"),
        )
    o.payment_status = PaymentStatus.refunded
    db.commit()
    return ok({"id": o.id, "payment_status": o.payment_status.value})
