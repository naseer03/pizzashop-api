from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.core.kitchen_hub import notify_kitchen_order_created
from app.schemas.cashier import (
    CashierCancelBody,
    CashierItemQuantityBody,
    CashierOrderCreate,
    CashierOrderItemAdd,
    CashierPayBody,
)
from app.services import cashier_orders, order_ops
from app.utils.responses import ok

router = APIRouter()


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
                    "created_at": r.created_at.isoformat().replace("+00:00", "Z") if r.created_at else None,
                }
                for r in rows
            ]
        }
    )


@router.get("/{order_id}/receipt")
def receipt(
    order_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    return ok(cashier_orders.receipt_json(db, order_id))


@router.get("/{order_id}/invoice")
def invoice(
    order_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    return ok(cashier_orders.invoice_json(db, order_id))


@router.get("/{order_id}")
def get_order(
    order_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.view"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.get_order(db, order_id)
    return ok(order_ops.order_detail_dict(db, o))


@router.post("/{order_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(
    order_id: int,
    body: CashierOrderItemAdd,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.add_line_item(db, order_id, body)
    return ok(order_ops.order_detail_dict(db, o))


@router.put("/{order_id}/items/{item_id}")
def update_item_qty(
    order_id: int,
    item_id: int,
    body: CashierItemQuantityBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.update_line_quantity(db, order_id, item_id, body)
    return ok(order_ops.order_detail_dict(db, o))


@router.delete("/{order_id}/items/{item_id}")
def remove_item(
    order_id: int,
    item_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.remove_line_item(db, order_id, item_id)
    return ok(order_ops.order_detail_dict(db, o))


@router.post("/{order_id}/pay")
def pay_order(
    order_id: int,
    body: CashierPayBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    result = cashier_orders.process_payment(db, order_id, body)
    return ok(result)


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    body: CashierCancelBody,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.cancel"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.cancel_order(db, order_id, body)
    return ok(order_ops.order_detail_dict(db, o))


@router.post("/{order_id}/hold")
def hold_order(
    order_id: int,
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("orders.update"))],
    db: Session = Depends(get_db),
):
    o = cashier_orders.hold_order(db, order_id)
    return ok(order_ops.order_detail_dict(db, o))
