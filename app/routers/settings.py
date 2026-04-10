from datetime import time, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import BusinessHour, DayOfWeek, NotificationSetting, PaymentSetting, StoreSetting
from app.schemas.ops import BusinessHourItem, PaymentsSettingsBody, StoreSettingsBody
from app.utils.responses import ok

router = APIRouter(prefix="/settings", tags=["settings"])


def _day_key(dow: Any) -> str:
    if isinstance(dow, DayOfWeek):
        return dow.value
    return str(dow).lower()


def _fmt_clock(t: Any) -> str:
    if t is None:
        return "00:00"
    if hasattr(t, "strftime"):
        return t.strftime("%H:%M")
    if isinstance(t, timedelta):
        secs = int(t.total_seconds()) % 86400
        h, rem = divmod(secs, 3600)
        m, _ = divmod(rem, 60)
        return f"{h:02d}:{m:02d}"
    s = str(t)
    return s[:5] if len(s) >= 5 else s


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
        "delivery_fee": float(s.delivery_fee),
        "min_order_for_free_delivery": float(s.min_order_for_free_delivery),
        "currency": s.currency,
        "currency_symbol": s.currency_symbol,
        "timezone": s.timezone,
    }


def _business_hours_list(db: Session) -> list[dict[str, Any]]:
    rows = db.query(BusinessHour).all()
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
        rows = db.query(BusinessHour).all()

    by_day: dict[str, BusinessHour] = {}
    for b in rows:
        by_day[_day_key(b.day_of_week)] = b

    # Always return 7 days (mon→sun); avoids frontend breaks when DB is partial.
    out: list[dict[str, Any]] = []
    for d in DayOfWeek:
        b = by_day.get(d.value)
        if b is None:
            out.append(
                {
                    "day": d.value,
                    "is_open": True,
                    "open_time": "10:00",
                    "close_time": "22:00",
                }
            )
        else:
            out.append(
                {
                    "day": d.value,
                    "is_open": bool(b.is_open),
                    "open_time": _fmt_clock(b.open_time),
                    "close_time": _fmt_clock(b.close_time),
                }
            )
    return out


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


def _payment_method_rows(db: Session) -> list[dict[str, Any]]:
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


def _payments_payload(db: Session) -> dict[str, Any]:
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return {
        "tax_rate": float(s.tax_rate),
        "delivery_fee": float(s.delivery_fee),
        "min_order_for_free_delivery": float(s.min_order_for_free_delivery),
        "payment_methods": _payment_method_rows(db),
    }


def _apply_payment_method_updates(db: Session, items: list[dict]) -> None:
    for item in items:
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


@router.get("/payments")
def get_payments(_: CurrentAdmin, db: Session = Depends(get_db)):
    return ok(_payments_payload(db))


@router.put("/payments")
def put_payments(body: PaymentsSettingsBody, _: CurrentAdmin, db: Session = Depends(get_db)):
    s = db.query(StoreSetting).first()
    if not s:
        s = StoreSetting()
        db.add(s)
        db.flush()
    if body.tax_rate is not None:
        s.tax_rate = body.tax_rate
    if body.delivery_fee is not None:
        s.delivery_fee = body.delivery_fee
    if body.min_order_for_free_delivery is not None:
        s.min_order_for_free_delivery = body.min_order_for_free_delivery
    if body.payment_methods is not None:
        _apply_payment_method_updates(db, body.payment_methods)
    db.commit()
    return ok(_payments_payload(db))
