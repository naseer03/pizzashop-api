from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CashierPrincipal, RequireCashierPermissions
from app.services.settings_payloads import payments_dict
from app.utils.responses import ok

router = APIRouter()


@router.get("")
def get_tax_settings(
    _: Annotated[CashierPrincipal, Depends(RequireCashierPermissions("menu.view"))],
    db: Session = Depends(get_db),
):
    """Authenticated shortcut for payment/tax fields. Prefer GET /v1/settings/general when no token."""
    return ok(payments_dict(db))
