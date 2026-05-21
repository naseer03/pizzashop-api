from pydantic import BaseModel, Field, field_validator, model_validator


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


def _normalize_category_ids(value: object) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return [int(p) for p in parts]
    if isinstance(value, list):
        if not value:
            return []
        if isinstance(value[0], dict):
            out: list[int] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                raw = item.get("id", item.get("category_id"))
                if raw is not None:
                    out.append(int(raw))
            return out
        return [int(v) for v in value]
    raise ValueError("category_ids must be a list of integers")


class ToppingCreate(BaseModel):
    name: str
    category_ids: list[int] = Field(
        min_length=1,
        description="Menu category ids (same `categories` table as menu items). At least one required.",
    )
    price: float
    is_available: bool = True
    sort_order: int = 0

    @model_validator(mode="before")
    @classmethod
    def _legacy_category_id(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "category_id" in data and "category_ids" not in data:
            data = {**data, "category_ids": [data["category_id"]]}
        if "category_ids" in data:
            data = {**data, "category_ids": _normalize_category_ids(data["category_ids"])}
        return data

    @field_validator("category_ids")
    @classmethod
    def _dedupe_category_ids(cls, v: list[int]) -> list[int]:
        seen: list[int] = []
        for cid in v:
            if cid not in seen:
                seen.append(cid)
        return seen


class CrustCreate(BaseModel):
    name: str
    category_ids: list[int] = Field(
        default_factory=list,
        description="Menu category ids; empty means available for all categories.",
    )
    price: float = 0
    is_available: bool = True
    sort_order: int = 0

    @model_validator(mode="before")
    @classmethod
    def _legacy_category_id(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "category_id" in data and "category_ids" not in data:
            cid = data["category_id"]
            data = {**data, "category_ids": [] if cid is None else [cid]}
        if "category_ids" in data:
            data = {**data, "category_ids": _normalize_category_ids(data["category_ids"])}
        return data

    @field_validator("category_ids")
    @classmethod
    def _dedupe_category_ids(cls, v: list[int]) -> list[int]:
        seen: list[int] = []
        for cid in v:
            if cid not in seen:
                seen.append(cid)
        return seen
