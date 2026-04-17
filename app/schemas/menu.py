from pydantic import BaseModel, Field


class MenuSizeIn(BaseModel):
    size: str
    price: float
    is_default: bool = False


class MenuItemCreate(BaseModel):
    name: str
    description: str | None = None
    category_id: int
    subcategory_id: int | None = None
    base_price: float
    sizes: list[MenuSizeIn] = Field(default_factory=list)
    is_available: bool = True
    is_featured: bool = False
    preparation_time_minutes: int = 15
    calories: int | None = None
    allergens: str | None = None


class MenuItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    base_price: float | None = None
    sizes: list[MenuSizeIn] | None = None
    is_available: bool | None = None
    is_featured: bool | None = None
    preparation_time_minutes: int | None = None
    calories: int | None = None
    allergens: str | None = None


class AvailabilityPatch(BaseModel):
    is_available: bool


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None
    has_sizes: bool = False
    display_order: int = 0


class SubcategoryCreate(BaseModel):
    name: str
    display_order: int = 0


class ToppingCreate(BaseModel):
    name: str
    category_id: int
    price: float
    is_available: bool = True
    sort_order: int = 0


class CrustCreate(BaseModel):
    name: str
    price: float = 0
    is_available: bool = True
    sort_order: int = 0
