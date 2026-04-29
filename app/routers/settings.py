from datetime import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import BusinessHour, CrustCategory, DayOfWeek, NotificationSetting, StoreSetting
from app.schemas.ops import (
    BusinessHoursUpdateBody,
    CrustCategoryCreate,
    PaymentsSettingsCreate,
    PaymentsSettingsBody,
    StoreSettingsBody,
    StoreSettingsCreate,
)
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


@router.get("/store", summary="Get store settings")
def get_store(_: CurrentAdmin, db: Session = Depends(get_db)):
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return ok(_store_dict(s))


@router.post(
    "/store",
    status_code=status.HTTP_201_CREATED,
    summary="Create store settings",
    description=(
        "Creates the first `store_settings` row when the table is empty (HTTP **201**). "
        "If a row already exists, returns **409** — use **PUT /v1/settings/store** to update."
    ),
    response_description="Created store profile (same shape as GET).",
    responses={
        201: {"description": "Store settings row created."},
        409: {"description": "Store settings already exist; use PUT to update."},
    },
)
def post_store(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    body: StoreSettingsCreate = Body(...),
):
    if db.query(StoreSetting).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err(
                "RESOURCE_CONFLICT",
                "Store settings already exist. Use PUT /v1/settings/store to update them.",
            ),
        )
    s = StoreSetting()
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.add(s)
    db.commit()
    db.refresh(s)
    return ok(_store_dict(s))


@router.put("/store", summary="Update store settings")
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
    body: BusinessHoursUpdateBody = Body(
        ...,
        openapi_examples={
            "full_week": {
                "summary": "Typical week",
                "value": {
                    "hours": [
                        {"day": "monday", "open_time": "10:00", "close_time": "22:00"},
                        {"day": "tuesday", "open_time": "10:00", "close_time": "22:00"},
                        {"day": "wednesday", "open_time": "10:00", "close_time": "22:00"},
                        {"day": "thursday", "open_time": "10:00", "close_time": "22:00"},
                        {"day": "friday", "open_time": "10:00", "close_time": "23:00"},
                        {"day": "saturday", "open_time": "10:00", "close_time": "23:00"},
                        {"day": "sunday", "open_time": "11:00", "close_time": "21:00"},
                    ]
                },
            }
        },
    ),
):
    for item in body.hours:
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
        b.is_open = (oh, om) != (ch, cm)
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


def _crust_category_dict(row: CrustCategory) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
    }


@router.get("/payments", summary="Get payment settings")
def get_payments(_: CurrentAdmin, db: Session = Depends(get_db)):
    return ok(_payments_payload(db))


@router.post(
    "/payments",
    status_code=status.HTTP_201_CREATED,
    summary="Create payment settings",
    description=(
        "Creates payment settings when `store_settings` does not exist yet (HTTP **201**). "
        "If payment settings already exist, returns **409** — use **PUT /v1/settings/payments** to update."
    ),
    response_description="Created payment settings.",
    responses={
        201: {"description": "Payment settings created."},
        409: {"description": "Payment settings already exist; use PUT to update."},
    },
)
def post_payments(
    _: CurrentAdmin,
    db: Session = Depends(get_db),
    body: PaymentsSettingsCreate = Body(...),
):
    if db.query(StoreSetting).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err(
                "RESOURCE_CONFLICT",
                "Payment settings already exist. Use PUT /v1/settings/payments to update them.",
            ),
        )

    s = StoreSetting()
    s.tax_rate = body.tax_rate
    s.delivery_fee = body.delivery_fee
    s.free_delivery_minimum_order = body.minimum_order_for_free_delivery
    db.add(s)
    db.commit()
    db.refresh(s)
    return ok(_payments_payload(db))


@router.put("/payments", summary="Update payment settings")
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


@router.get("/crust-categories", summary="List crust categories")
def get_crust_categories(_: CurrentAdmin, db: Session = Depends(get_db)):
    rows = db.query(CrustCategory).order_by(CrustCategory.sort_order, CrustCategory.id).all()
    return ok([_crust_category_dict(row) for row in rows])


@router.post(
    "/crust-categories",
    status_code=status.HTTP_201_CREATED,
    summary="Create crust category",
)
def post_crust_category(
    body: CrustCategoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)
):
    row = CrustCategory(name=body.name.strip(), sort_order=body.sort_order, is_active=body.is_active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_crust_category_dict(row))
