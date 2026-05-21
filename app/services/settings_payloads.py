"""Read-only settings payloads shared by admin, public, and cashier routes."""

from __future__ import annotations

from datetime import time
from typing import Any

from sqlalchemy.orm import Session

from app.models import BusinessHour, DayOfWeek, StoreSetting


def store_dict(s: StoreSetting) -> dict[str, Any]:
    return {
        "store_name": s.store_name,
        "address_line1": s.address_line1,
        "address_line2": s.address_line2,
        "city": s.city,
        "state": s.state,
        "postal_code": s.postal_code,
        "country": s.country,
        "phone": s.phone,
        "email": s.email,
        "website": s.website,
        "logo_url": s.logo_url,
        "currency": s.currency,
        "currency_symbol": s.currency_symbol,
        "timezone": s.timezone,
    }


def business_hours_list(db: Session) -> list[dict[str, Any]]:
    rows = db.query(BusinessHour).order_by(BusinessHour.id).all()
    if not rows:
        for d in DayOfWeek:
            db.add(
                BusinessHour(
                    day_of_week=d,
                    is_open=True,
                    open_time=time(10, 0),
                    close_time=time(22, 0),
                )
            )
        db.commit()
        rows = db.query(BusinessHour).order_by(BusinessHour.id).all()
    order = list(DayOfWeek)
    rows = sorted(rows, key=lambda x: order.index(x.day_of_week))
    return [
        {
            "day": b.day_of_week.value,
            "is_open": b.is_open,
            "open_time": b.open_time.strftime("%H:%M"),
            "close_time": b.close_time.strftime("%H:%M"),
        }
        for b in rows
    ]


def ensure_store_row(db: Session) -> StoreSetting:
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def payments_dict(db: Session) -> dict[str, Any]:
    s = ensure_store_row(db)
    return {
        "tax_rate": float(s.tax_rate),
        "delivery_fee": float(s.delivery_fee),
        "minimum_order_for_free_delivery": float(s.free_delivery_minimum_order),
    }


def general_settings_dict(db: Session) -> dict[str, Any]:
    """Store profile, hours, and payment/tax fields safe for POS and public displays."""
    store = ensure_store_row(db)
    return {
        "store": store_dict(store),
        "business_hours": business_hours_list(db),
        "payments": payments_dict(db),
    }
