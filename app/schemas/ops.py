from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


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


class BusinessHourItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    day: str = Field(validation_alias=AliasChoices("day", "dayOfWeek", "day_of_week"))
    is_open: bool = Field(default=True, validation_alias=AliasChoices("is_open", "isOpen"))
    open_time: str = Field(default="10:00", validation_alias=AliasChoices("open_time", "openTime"))
    close_time: str = Field(default="22:00", validation_alias=AliasChoices("close_time", "closeTime"))

    @field_validator("day", mode="before")
    @classmethod
    def normalize_day(cls, v: object) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return str(v).strip().lower()


class PaymentsSettingsBody(BaseModel):
    tax_rate: float | None = None
    delivery_fee: float | None = None
    minimum_order_for_free_delivery: float | None = Field(
        default=None,
        description="Subtotal at or above this waives delivery fee; 0 disables free-delivery threshold.",
    )


class ReportExportBody(BaseModel):
    report_type: str
    format: str
    date_from: str | None = None
    date_to: str | None = None
