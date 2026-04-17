from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    currency: str | None = None
    currency_symbol: str | None = None
    timezone: str | None = None


class StoreSettingsCreate(StoreSettingsBody):
    """Body for POST /settings/store — same fields as update, but store_name is required."""

    model_config = ConfigDict(extra="forbid")

    store_name: str = Field(min_length=1, max_length=200)


class BusinessHourItem(BaseModel):
    """One row of store hours (used inside PUT /settings/business-hours)."""

    model_config = ConfigDict(extra="forbid")

    day: str = Field(description="Day of week, e.g. monday, tuesday (lowercase enum value).")
    open_time: str = Field(description="Opening time HH:MM (24h).")
    close_time: str = Field(description="Closing time HH:MM (24h). Match open_time for a closed day.")

    @field_validator("day", mode="before")
    @classmethod
    def normalize_day(cls, v: object) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return str(v).strip().lower()


class BusinessHoursUpdateBody(BaseModel):
    """Request body for PUT /settings/business-hours (object wrapper so OpenAPI / Swagger UI show fields correctly)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "hours": [
                    {"day": "monday", "open_time": "10:00", "close_time": "22:00"},
                    {"day": "tuesday", "open_time": "10:00", "close_time": "22:00"},
                    {"day": "wednesday", "open_time": "10:00", "close_time": "22:00"},
                    {"day": "thursday", "open_time": "10:00", "close_time": "22:00"},
                    {"day": "friday", "open_time": "10:00", "close_time": "23:00"},
                    {"day": "saturday", "open_time": "10:00", "close_time": "23:00"},
                    {"day": "sunday", "open_time": "11:00", "close_time": "21:00"},
                ]
            }
        },
    )

    hours: list[BusinessHourItem] = Field(
        ...,
        min_length=1,
        description="List of day schedules. Each entry uses day, open_time, and close_time only.",
    )


class PaymentsSettingsBody(BaseModel):
    tax_rate: float | None = None
    delivery_fee: float | None = None
    minimum_order_for_free_delivery: float | None = Field(
        default=None,
        description="Subtotal at or above this waives delivery fee; 0 disables free-delivery threshold.",
    )


class PaymentsSettingsCreate(PaymentsSettingsBody):
    """Body for POST /settings/payments — same fields as update, but all are required."""

    model_config = ConfigDict(extra="forbid")

    tax_rate: float
    delivery_fee: float
    minimum_order_for_free_delivery: float = Field(
        description="Subtotal at or above this waives delivery fee; 0 disables free-delivery threshold.",
    )


class ReportExportBody(BaseModel):
    report_type: str
    format: str
    date_from: str | None = None
    date_to: str | None = None
