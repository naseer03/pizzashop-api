from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.orders import OrderItemIn


class CashierLoginBody(BaseModel):
    email: EmailStr
    password: str


class CashierOrderCreate(BaseModel):
    order_type: str
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    table_number: str | None = None
    delivery_address: str | None = None
    delivery_instructions: str | None = None
    items: list[OrderItemIn]
    discount_code: str | None = None
    notes: str | None = None
    payment_method: str = "cash"


class CashierOrderItemAdd(BaseModel):
    item: OrderItemIn


class CashierItemQuantityBody(BaseModel):
    quantity: int = Field(..., ge=1)


class CashierPayBody(BaseModel):
    payment_method: str
    amount_received: Decimal | None = None


class CashierCancelBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)
