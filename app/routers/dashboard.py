from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Inventory, Order, OrderItem, OrderStatus, PaymentStatus
from app.utils.responses import ok

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _parse_day(d: str | None) -> date | None:
    if not d:
        return None
    return date.fromisoformat(d)


@router.get("/stats")
def dashboard_stats(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
):
    df = _parse_day(date_from)
    dt = _parse_day(date_to)
    q = db.query(Order)
    if df:
        q = q.filter(func.date(Order.created_at) >= df)
    if dt:
        q = q.filter(func.date(Order.created_at) <= dt)
    total_orders = q.filter(Order.status != OrderStatus.cancelled).count()
    revenue = (
        q.filter(Order.payment_status == PaymentStatus.paid, Order.status != OrderStatus.cancelled)
        .with_entities(func.coalesce(func.sum(Order.total_amount), 0))
        .scalar()
    )
    if revenue is None:
        revenue = Decimal("0")
    active_statuses = (
        OrderStatus.pending,
        OrderStatus.confirmed,
        OrderStatus.preparing,
        OrderStatus.ready,
        OrderStatus.out_for_delivery,
    )
    active_orders = q.filter(Order.status.in_(active_statuses)).count()
    low_stock = (
        db.query(Inventory)
        .filter(Inventory.is_active.is_(True), Inventory.current_stock < Inventory.min_stock_level)
        .count()
    )

    prev_len = 30
    end_prev = df or date.today()
    start_prev = end_prev - timedelta(days=prev_len)
    q_prev = db.query(Order).filter(
        func.date(Order.created_at) >= start_prev,
        func.date(Order.created_at) < end_prev,
        Order.status != OrderStatus.cancelled,
    )
    prev_orders = q_prev.count()
    prev_rev = q_prev.filter(Order.payment_status == PaymentStatus.paid).with_entities(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).scalar() or Decimal("0")

    orders_change = 0.0
    revenue_change = 0.0
    if prev_orders:
        orders_change = round((total_orders - prev_orders) / prev_orders * 100, 1)
    if prev_rev and prev_rev > 0:
        revenue_change = round(float((revenue - prev_rev) / prev_rev * 100), 1)

    return ok(
        {
            "total_orders": total_orders,
            "total_revenue": float(revenue),
            "active_orders": active_orders,
            "low_stock_items": low_stock,
            "orders_change_percent": orders_change,
            "revenue_change_percent": revenue_change,
        }
    )


@router.get("/sales-chart")
def sales_chart(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    period: Annotated[str, Query()] = "daily",
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
):
    df = _parse_day(date_from) or (date.today() - timedelta(days=6))
    dt = _parse_day(date_to) or date.today()
    q = db.query(
        func.date(Order.created_at).label("d"),
        func.count(Order.id),
        func.coalesce(func.sum(Order.total_amount), 0),
    ).filter(
        func.date(Order.created_at) >= df,
        func.date(Order.created_at) <= dt,
        Order.status != OrderStatus.cancelled,
    )
    rows = q.group_by(func.date(Order.created_at)).order_by("d").all()
    labels = [r[0].strftime("%a") if hasattr(r[0], "strftime") else str(r[0]) for r in rows]
    orders_counts = [int(r[1]) for r in rows]
    revenue_vals = [float(r[2]) for r in rows]
    if not labels:
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        orders_counts = [0] * 7
        revenue_vals = [0.0] * 7
    return ok({"labels": labels, "datasets": {"orders": orders_counts, "revenue": revenue_vals}})


@router.get("/recent-orders")
def recent_orders(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    rows = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for o in rows:
        items_count = (
            db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
            .filter(OrderItem.order_id == o.id)
            .scalar()
        )
        out.append(
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
    return ok(out)
