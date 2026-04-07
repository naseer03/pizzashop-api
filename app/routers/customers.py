from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Customer, Order
from app.schemas.ops import CustomerCreate, LoyaltyPatch
from app.utils.responses import err, ok

router = APIRouter(prefix="/customers", tags=["customers"])


def _cust_dict(c: Customer, db: Session) -> dict:
    last_order = (
        db.query(Order)
        .filter(Order.customer_id == c.id)
        .order_by(Order.created_at.desc())
        .first()
    )
    return {
        "id": c.id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "email": c.email,
        "phone": c.phone,
        "address": {
            "line1": c.address_line1,
            "line2": c.address_line2,
            "city": c.city,
            "state": c.state,
            "postal_code": c.postal_code,
        },
        "total_orders": c.total_orders,
        "total_spent": float(c.total_spent),
        "loyalty_points": c.loyalty_points,
        "last_order_at": last_order.created_at.isoformat().replace("+00:00", "Z")
        if last_order and last_order.created_at
        else None,
        "created_at": c.created_at.isoformat().replace("+00:00", "Z") if c.created_at else None,
    }


@router.get("")
def list_customers(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_order: Annotated[str, Query()] = "desc",
):
    q = db.query(Customer).filter(Customer.is_active.is_(True))
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                Customer.first_name.like(term),
                Customer.last_name.like(term),
                Customer.email.like(term),
                Customer.phone.like(term),
            )
        )
    col = Customer.created_at
    if sort_by == "total_orders":
        col = Customer.total_orders
    elif sort_by == "total_spent":
        col = Customer.total_spent
    q = q.order_by(col.asc() if sort_order == "asc" else col.desc())
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return ok(
        {
            "customers": [_cust_dict(c, db) for c in rows],
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total,
                "total_pages": total_pages,
            },
        }
    )


@router.get("/{customer_id}")
def get_customer(customer_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Customer not found"),
        )
    orders = (
        db.query(Order).filter(Order.customer_id == customer_id).order_by(Order.created_at.desc()).limit(20).all()
    )
    data = _cust_dict(c, db)
    data["orders"] = [
        {
            "id": o.id,
            "order_number": o.order_number,
            "total_amount": float(o.total_amount),
            "status": o.status.value,
            "created_at": o.created_at.isoformat().replace("+00:00", "Z") if o.created_at else None,
        }
        for o in orders
    ]
    return ok(data)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(body: CustomerCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = Customer(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
        address_line1=body.address_line1,
        city=body.city,
        state=body.state,
        postal_code=body.postal_code,
        notes=body.notes,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return ok(_cust_dict(c, db))


@router.put("/{customer_id}")
def update_customer(customer_id: int, body: CustomerCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Customer not found"),
        )
    c.first_name = body.first_name
    c.last_name = body.last_name
    c.email = body.email
    c.phone = body.phone
    c.address_line1 = body.address_line1
    c.city = body.city
    c.state = body.state
    c.postal_code = body.postal_code
    c.notes = body.notes
    db.commit()
    db.refresh(c)
    return ok(_cust_dict(c, db))


@router.get("/{customer_id}/orders")
def customer_orders(
    customer_id: int,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if not db.get(Customer, customer_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Customer not found"),
        )
    q = db.query(Order).filter(Order.customer_id == customer_id).order_by(Order.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    return ok(
        {
            "orders": [
                {
                    "id": o.id,
                    "order_number": o.order_number,
                    "total_amount": float(o.total_amount),
                    "status": o.status.value,
                    "created_at": o.created_at.isoformat().replace("+00:00", "Z") if o.created_at else None,
                }
                for o in rows
            ],
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total,
                "total_pages": max(1, (total + per_page - 1) // per_page),
            },
        }
    )


@router.patch("/{customer_id}/loyalty-points")
def loyalty_points(customer_id: int, body: LoyaltyPatch, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Customer not found"),
        )
    if body.action == "add":
        c.loyalty_points += body.points
    elif body.action == "remove":
        c.loyalty_points = max(0, c.loyalty_points - body.points)
    else:
        c.loyalty_points = body.points
    db.commit()
    db.refresh(c)
    return ok({"loyalty_points": c.loyalty_points})


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_customer(customer_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Customer not found"),
        )
    c.is_active = False
    db.commit()
    return None
