from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class OrderItemToppingIn(BaseModel):
    topping_id: int
    quantity: int = 1


class OrderItemIn(BaseModel):
    menu_item_id: int
    size: str | None = None
    crust_id: int | None = None
    toppings: list[OrderItemToppingIn] = Field(default_factory=list)
    quantity: int = 1
    special_instructions: str | None = None


class OrderCreate(BaseModel):
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    order_type: str
    table_number: str | None = None
    delivery_address: str | None = None
    delivery_instructions: str | None = None
    items: list[OrderItemIn]
    discount_code: str | None = None
    payment_method: str = "cash"
    notes: str | None = None


class OrderUpdate(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    table_number: str | None = None
    delivery_address: str | None = None
    delivery_instructions: str | None = None
    notes: str | None = None


class OrderStatusPatch(BaseModel):
    status: str
    estimated_ready_time: str | None = None


class OrderAssignPatch(BaseModel):
    employee_id: int


class OrderCancelBody(BaseModel):
    reason: str
