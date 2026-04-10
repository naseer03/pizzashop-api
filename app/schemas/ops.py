from pydantic import BaseModel


class InventoryCreate(BaseModel):
    name: str
    sku: str | None = None
    category: str
    unit: str
    current_stock: float = 0
    min_stock_level: float = 0
    reorder_level: float = 0
    unit_cost: float = 0
    supplier_name: str | None = None
    supplier_contact: str | None = None


class StockPatch(BaseModel):
    action: str
    quantity: float
    notes: str | None = None


class CustomerCreate(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    phone: str
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    notes: str | None = None


class LoyaltyPatch(BaseModel):
    action: str
    points: int
    reason: str | None = None


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    role_id: int
    hourly_rate: float = 0
    hire_date: str
    date_of_birth: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    schedule: list[dict] | None = None


class EmployeeStatusPatch(BaseModel):
    status: str


class EmployeeScheduleBody(BaseModel):
    schedule: list[dict]


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    color: str = "#6B7280"
    permission_ids: list[int] | None = None


class RolePermissionsBody(BaseModel):
    permission_ids: list[int]


class StoreSettingsBody(BaseModel):
    store_name: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    logo_url: str | None = None
    tax_rate: float | None = None
    delivery_fee: float | None = None
    min_order_for_free_delivery: float | None = None
    currency: str | None = None
    currency_symbol: str | None = None
    timezone: str | None = None


class PaymentsSettingsBody(BaseModel):
    """Tax rate is a percentage (e.g. 8.0 = 8%). If subtotal >= min_order_for_free_delivery (> 0), delivery fee is waived."""

    tax_rate: float | None = None
    delivery_fee: float | None = None
    min_order_for_free_delivery: float | None = None
    payment_methods: list[dict] | None = None


class BusinessHourItem(BaseModel):
    day: str
    is_open: bool = True
    open_time: str = "10:00"
    close_time: str = "22:00"


class ReportExportBody(BaseModel):
    report_type: str
    format: str
    date_from: str | None = None
    date_to: str | None = None
