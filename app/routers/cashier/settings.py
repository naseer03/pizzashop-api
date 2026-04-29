from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.models import StoreSetting
from app.utils.responses import ok

router = APIRouter()


@router.get("")
def get_tax_settings(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
):
    row = db.query(StoreSetting).first()
    if not row:
        row = StoreSetting()
        db.add(row)
        db.commit()
        db.refresh(row)
    return ok({"tax_rate": float(row.tax_rate)})
