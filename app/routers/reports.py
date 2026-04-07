from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Order, OrderItem, OrderStatus, PaymentMethod, PaymentStatus
from app.schemas.ops import ReportExportBody
from app.utils.responses import ok

router = APIRouter(prefix="/reports", tags=["reports"])


def _daterange(
    date_from: str | None, date_to: str | None
) -> tuple[date | None, date | None]:
    df = date.fromisoformat(date_from) if date_from else None
    dt = date.fromisoformat(date_to) if date_to else None
    return df, dt


@router.get("/sales")
def sales_report(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    group_by: Annotated[str, Query()] = "day",
):
    df, dt = _daterange(date_from, date_to)

    def base_orders():
        q = db.query(Order).filter(Order.status != OrderStatus.cancelled)
        if df:
            q = q.filter(func.date(Order.created_at) >= df)
        if dt:
            q = q.filter(func.date(Order.created_at) <= dt)
        return q

    paid_orders = base_orders().filter(Order.payment_status == PaymentStatus.paid)
    total_revenue = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .select_from(Order)
        .filter(Order.status != OrderStatus.cancelled, Order.payment_status == PaymentStatus.paid)
    )
    if df:
        total_revenue = total_revenue.filter(func.date(Order.created_at) >= df)
    if dt:
        total_revenue = total_revenue.filter(func.date(Order.created_at) <= dt)
    total_revenue = total_revenue.scalar() or Decimal("0")
    total_orders = paid_orders.count()

    items_q = (
        db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.status != OrderStatus.cancelled)
    )
    if df:
        items_q = items_q.filter(func.date(Order.created_at) >= df)
    if dt:
        items_q = items_q.filter(func.date(Order.created_at) <= dt)
    total_items_sold = int(items_q.scalar() or 0)
    aov = float(total_revenue / total_orders) if total_orders else 0.0

    by_day = (
        db.query(
            func.date(Order.created_at),
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0),
        )
        .filter(Order.status != OrderStatus.cancelled, Order.payment_status == PaymentStatus.paid)
    )
    if df:
        by_day = by_day.filter(func.date(Order.created_at) >= df)
    if dt:
        by_day = by_day.filter(func.date(Order.created_at) <= dt)
    by_period = [
        {"date": str(r[0]), "orders": int(r[1]), "revenue": float(r[2])}
        for r in by_day.group_by(func.date(Order.created_at)).all()
    ]

    type_q = (
        db.query(Order.order_type, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.status != OrderStatus.cancelled, Order.payment_status == PaymentStatus.paid)
    )
    if df:
        type_q = type_q.filter(func.date(Order.created_at) >= df)
    if dt:
        type_q = type_q.filter(func.date(Order.created_at) <= dt)
    by_type = {
        r[0].value: {"orders": int(r[1]), "revenue": float(r[2])} for r in type_q.group_by(Order.order_type).all()
    }

    pay_q = (
        db.query(Order.payment_method, func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.status != OrderStatus.cancelled, Order.payment_status == PaymentStatus.paid)
    )
    if df:
        pay_q = pay_q.filter(func.date(Order.created_at) >= df)
    if dt:
        pay_q = pay_q.filter(func.date(Order.created_at) <= dt)
    by_pay = {
        r[0].value: {"orders": int(r[1]), "revenue": float(r[2])}
        for r in pay_q.group_by(Order.payment_method).all()
    }

    return ok(
        {
            "summary": {
                "total_revenue": float(total_revenue),
                "total_orders": total_orders,
                "average_order_value": round(aov, 2),
                "total_items_sold": total_items_sold,
            },
            "by_period": by_period,
            "by_order_type": by_type,
            "by_payment_method": by_pay,
        }
    )


@router.get("/top-items")
def top_items(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    df, dt = _daterange(date_from, date_to)
    q = (
        db.query(
            OrderItem.menu_item_id,
            OrderItem.menu_item_name,
            func.sum(OrderItem.quantity),
            func.coalesce(func.sum(OrderItem.total_price), 0),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.status != OrderStatus.cancelled)
    )
    if df:
        q = q.filter(func.date(Order.created_at) >= df)
    if dt:
        q = q.filter(func.date(Order.created_at) <= dt)
    rows = (
        q.group_by(OrderItem.menu_item_id, OrderItem.menu_item_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return ok(
        [
            {
                "menu_item_id": r[0],
                "name": r[1],
                "category": "",
                "total_quantity": int(r[2]),
                "total_revenue": float(r[3]),
            }
            for r in rows
        ]
    )


@router.get("/orders")
def orders_report(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
):
    df, dt = _daterange(date_from, date_to)
    q = db.query(Order)
    if df:
        q = q.filter(func.date(Order.created_at) >= df)
    if dt:
        q = q.filter(func.date(Order.created_at) <= dt)
    total = q.count()
    cancelled = q.filter(Order.status == OrderStatus.cancelled).count()
    return ok(
        {
            "total_orders": total,
            "cancelled": cancelled,
            "completed": q.filter(Order.status == OrderStatus.completed).count(),
        }
    )


@router.get("/inventory")
def inventory_report(_: CurrentAdmin, db: Session = Depends(get_db)):
    from app.models import Inventory

    rows = db.query(Inventory).filter(Inventory.is_active.is_(True)).all()
    low = sum(1 for r in rows if r.current_stock < r.min_stock_level)
    return ok({"total_skus": len(rows), "low_stock": low})


@router.get("/employees")
def employees_report(_: CurrentAdmin, db: Session = Depends(get_db)):
    from app.models import Employee, EmployeeStatus

    active = db.query(Employee).filter(Employee.status == EmployeeStatus.active).count()
    return ok({"active_employees": active})


@router.post("/export")
def export_report(_: CurrentAdmin, body: ReportExportBody):
    return ok(
        {
            "message": "Export queued",
            "report_type": body.report_type,
            "format": body.format,
            "date_from": body.date_from,
            "date_to": body.date_to,
        }
    )
