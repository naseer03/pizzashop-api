from datetime import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import BusinessHour, DayOfWeek, NotificationSetting, StoreSetting
from app.schemas.ops import BusinessHourItem, PaymentsSettingsBody, StoreSettingsBody
from app.utils.responses import err, ok

router = APIRouter(prefix="/settings", tags=["settings"])


def _store_dict(s: StoreSetting) -> dict:
    return {
        "store_name": s.store_name,
        "address_line1": s.address_line1,
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


def _business_hours_list(db: Session) -> list[dict[str, Any]]:
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


@router.get("/store")
def get_store(_: CurrentAdmin, db: Session = Depends(get_db)):
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return ok(_store_dict(s))


@router.put("/store")
def put_store(body: StoreSettingsBody, _: CurrentAdmin, db: Session = Depends(get_db)):
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.flush()
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return ok(_store_dict(s))


@router.get("/business-hours")
def get_business_hours(_: CurrentAdmin, db: Session = Depends(get_db)):
    return ok(_business_hours_list(db))


def _unwrap_business_hours_json(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # Common wrappers:
        # - { data: [...] }
        # - { success: true, data: [...] }
        # - { success: true, data: { data: [...] } }
        # - { business_hours: [...] } / { businessHours: [...] } / { hours: [...] }
        for key in ("data", "businessHours", "business_hours", "hours"):
            v = raw.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                try:
                    return _unwrap_business_hours_json(v)
                except ValueError:
                    pass
    raise ValueError(
        "Send a JSON array of hours, or an object with a list under "
        "data, businessHours, business_hours, or hours."
    )


def _hh_mm(s: str) -> tuple[int, int]:
    parts = s.strip().split(":")
    if len(parts) < 2:
        raise ValueError(f"Time must be HH:MM (e.g. 09:30), got {s!r}")
    oh, om = int(parts[0]), int(parts[1])
    if not (0 <= oh <= 23 and 0 <= om <= 59):
        raise ValueError(f"Time out of range: {s!r}")
    return oh, om


@router.put("/business-hours")
def put_business_hours(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    body: Any = Body(...),
):
    try:
        payload = _unwrap_business_hours_json(body)
        items = TypeAdapter(list[BusinessHourItem]).validate_python(payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err("VALIDATION_ERROR", str(e)),
        ) from None
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err(
                "VALIDATION_ERROR",
                "Invalid business hours entry.",
                details={"errors": e.errors(include_url=False)},
            ),
        ) from None

    for item in items:
        try:
            dow = DayOfWeek(item.day)
        except ValueError:
            allowed = ", ".join(d.value for d in DayOfWeek)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err(
                    "VALIDATION_ERROR",
                    f"Invalid day {item.day!r}. Expected one of: {allowed}",
                ),
            ) from None
        b = db.query(BusinessHour).filter(BusinessHour.day_of_week == dow).first()
        if not b:
            b = BusinessHour(day_of_week=dow)
            db.add(b)
            db.flush()
        b.is_open = item.is_open
        try:
            oh, om = _hh_mm(item.open_time)
            ch, cm = _hh_mm(item.close_time)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err("VALIDATION_ERROR", str(e)),
            ) from None
        b.open_time = time(oh, om)
        b.close_time = time(ch, cm)
    db.commit()
    return ok(_business_hours_list(db))


@router.get("/notifications")
def get_notifications(_: CurrentAdmin, db: Session = Depends(get_db)):
    rows = db.query(NotificationSetting).order_by(NotificationSetting.id).all()
    return ok(
        {r.setting_key: r.setting_value for r in rows}
        if rows
        else {"email_orders": True, "sms_low_stock": False}
    )


@router.put("/notifications")
def put_notifications(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    body: dict[str, bool] = Body(...),
):
    for k, v in body.items():
        row = db.query(NotificationSetting).filter(NotificationSetting.setting_key == k).first()
        if not row:
            row = NotificationSetting(setting_key=k)
            db.add(row)
            db.flush()
        row.setting_value = bool(v)
    db.commit()
    rows = db.query(NotificationSetting).order_by(NotificationSetting.id).all()
    return ok({r.setting_key: r.setting_value for r in rows})


def _store_for_payments(db: Session) -> StoreSetting:
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _payments_payload(db: Session) -> dict[str, Any]:
    s = _store_for_payments(db)
    return {
        "tax_rate": float(s.tax_rate),
        "delivery_fee": float(s.delivery_fee),
        "minimum_order_for_free_delivery": float(s.free_delivery_minimum_order),
    }


@router.get("/payments")
def get_payments(_: CurrentAdmin, db: Session = Depends(get_db)):
    return ok(_payments_payload(db))


@router.put("/payments")
def put_payments(body: PaymentsSettingsBody, _: CurrentAdmin, db: Session = Depends(get_db)):
    s = _store_for_payments(db)
    data = body.model_dump(exclude_unset=True)
    if "tax_rate" in data:
        s.tax_rate = data["tax_rate"]
    if "delivery_fee" in data:
        s.delivery_fee = data["delivery_fee"]
    if "minimum_order_for_free_delivery" in data:
        s.free_delivery_minimum_order = data["minimum_order_for_free_delivery"]
    db.commit()
    db.refresh(s)
    return ok(_payments_payload(db))
