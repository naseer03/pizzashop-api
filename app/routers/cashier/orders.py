from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.core.kitchen_hub import notify_kitchen_order_created
from app.models import Order
from app.schemas.cashier import (
    CashierCancelBody,
    CashierItemQuantityBody,
    CashierOrderCommentsBody,
    CashierOrderCreate,
    CashierOrderItemAdd,
    CashierPayBody,
)
from app.services import cashier_orders, order_ops
from app.utils.responses import ok

router = APIRouter()


def resolve_cashier_order(
    order_ref: str,
    db: Session = Depends(get_db),
) -> Order:
    return cashier_orders.resolve_order_ref(db, order_ref)


async def _broadcast_new_order(order_id: int) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        o = cashier_orders.get_order(db, order_id)
        summary = {
            "id": o.id,
            "order_number": o.order_number,
            "status": o.status.value,
            "total_amount": float(o.total_amount),
            "items": [
                {"name": li.menu_item_name, "qty": li.quantity, "size": li.size.value if li.size else None}
                for li in o.items
            ],
        }
        await notify_kitchen_order_created(summary)
    finally:
        db.close()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(
    body: CashierOrderCreate,
    bg: BackgroundTasks,
    principal: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.create"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.create_order(db, principal, body)
    bg.add_task(_broadcast_new_order, o.id)
    return ok(order_ops.order_detail_dict(db, o))


@router.get("/active")
def list_active_orders(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    rows = cashier_orders.list_active_orders(db)
    return ok(
        {
            "orders": [
                {
                    "id": r.id,
                    "order_number": r.order_number,
                    "status": r.status.value,
                    "payment_status": r.payment_status.value,
                    "kot_printed": r.kot_printed,
                    "total_amount": float(r.total_amount),
                    "comments": r.notes,
                    "created_at": r.created_at.isoformat().replace("+00:00", "Z") if r.created_at else None,
                }
                for r in rows
            ]
        }
    )


@router.get("/search")
def search_order(
    order_number: Annotated[
        str,
        Query(
            min_length=1,
            description="Order number to look up, e.g. ORD-2026-001. "
            "A partial value is allowed when it matches exactly one order.",
        ),
    ],
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.find_order_by_order_number(db, order_number)
    return ok(order_ops.order_detail_dict(db, o))


@router.get("/{order_ref}/receipt")
def receipt(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    return ok(cashier_orders.receipt_json(db, order.id))


@router.get("/{order_ref}/invoice")
def invoice(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    return ok(cashier_orders.invoice_json(db, order.id))


@router.get("/{order_ref}")
def get_order(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    return ok(order_ops.order_detail_dict(db, order))


@router.patch("/{order_ref}/comments")
def patch_order_comments(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    body: CashierOrderCommentsBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.update_order_comments(db, order.id, body.comments)
    return ok(order_ops.order_detail_dict(db, o))


@router.post("/{order_ref}/items", status_code=status.HTTP_201_CREATED)
def add_item(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    body: CashierOrderItemAdd,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.add_line_item(db, order.id, body)
    return ok(order_ops.order_detail_dict(db, o))


@router.put("/{order_ref}/items/{item_id}")
def update_item_qty(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    item_id: int,
    body: CashierItemQuantityBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.update_line_quantity(db, order.id, item_id, body)
    return ok(order_ops.order_detail_dict(db, o))


@router.delete("/{order_ref}/items/{item_id}")
def remove_item(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    item_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.remove_line_item(db, order.id, item_id)
    return ok(order_ops.order_detail_dict(db, o))


@router.post("/{order_ref}/pay")
def pay_order(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    body: CashierPayBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    result = cashier_orders.process_payment(db, order.id, body)
    return ok(result)


@router.post("/{order_ref}/cancel")
def cancel_order(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    body: CashierCancelBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.cancel"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.cancel_order(db, order.id, body)
    return ok(order_ops.order_detail_dict(db, o))


@router.post("/{order_ref}/hold")
def hold_order(
    order: Annotated[Order, Depends(resolve_cashier_order)],
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.hold_order(db, order.id)
    return ok(order_ops.order_detail_dict(db, o))
