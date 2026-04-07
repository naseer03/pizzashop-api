from datetime import time
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import BusinessHour, DayOfWeek, NotificationSetting, PaymentSetting, StoreSetting
from app.schemas.ops import BusinessHourItem, StoreSettingsBody
from app.utils.responses import ok

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
        "tax_rate": float(s.tax_rate),
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


@router.put("/business-hours")
def put_business_hours(body: list[BusinessHourItem], _: CurrentAdmin, db: Session = Depends(get_db)):
    for item in body:
        try:
            dow = DayOfWeek(item.day)
        except ValueError:
            continue
        b = db.query(BusinessHour).filter(BusinessHour.day_of_week == dow).first()
        if not b:
            b = BusinessHour(day_of_week=dow)
            db.add(b)
            db.flush()
        b.is_open = item.is_open
        oh, om = map(int, item.open_time.split(":")[:2])
        ch, cm = map(int, item.close_time.split(":")[:2])
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


def _payments_list(db: Session) -> list[dict[str, Any]]:
    rows = db.query(PaymentSetting).order_by(PaymentSetting.id).all()
    return [
        {
            "method": r.payment_method,
            "is_enabled": r.is_enabled,
            "display_name": r.display_name,
            "processing_fee_percent": float(r.processing_fee_percent),
            "min_order_amount": float(r.min_order_amount),
        }
        for r in rows
    ]


@router.get("/payments")
def get_payments(_: CurrentAdmin, db: Session = Depends(get_db)):
    return ok(_payments_list(db))


@router.put("/payments")
def put_payments(body: list[dict], _: CurrentAdmin, db: Session = Depends(get_db)):
    for item in body:
        mid = item.get("payment_method") or item.get("method")
        if not mid:
            continue
        r = db.query(PaymentSetting).filter(PaymentSetting.payment_method == mid).first()
        if not r:
            r = PaymentSetting(payment_method=mid)
            db.add(r)
            db.flush()
        if "is_enabled" in item:
            r.is_enabled = item["is_enabled"]
        if "display_name" in item:
            r.display_name = item["display_name"]
        if "processing_fee_percent" in item:
            r.processing_fee_percent = item["processing_fee_percent"]
        if "min_order_amount" in item:
            r.min_order_amount = item["min_order_amount"]
    db.commit()
    return ok(_payments_list(db))
