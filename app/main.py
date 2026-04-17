import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.bootstrap import seed_if_empty
from app.core.exception_handlers import register_exception_handlers
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import (
    auth,
    categories,
    crusts,
    customers,
    dashboard,
    employees,
    inventory,
    menu_items,
    orders,
    reports,
    roles,
    settings as settings_router,
    toppings,
)

log = logging.getLogger("uvicorn.error")

API_DESCRIPTION = """
REST API for the PizzaHub point-of-sale admin backend.

## Base URL
All versioned routes are under **`/v1`**. Example: `GET /v1/auth/me`.

Interactive docs: **`/docs`** (Swagger UI), **`/redoc`** (ReDoc), **`/openapi.json`** (OpenAPI schema).

## Authentication
1. Call **`POST /v1/auth/login`** with email and password.
2. Copy `data.access_token` from the response.
3. In Swagger UI, click **Authorize** and enter a value. Use either the raw JWT or the form `Bearer <token>` depending on your client; the UI typically sends `Authorization: Bearer …`.
4. Protected routes require a valid JWT access token.

## Response shape
Successful responses wrap payloads as `{ "success": true, "data": ... }`.
Errors use `{ "success": false, "error": { "code", "message", ... } }` with appropriate HTTP status codes.

## Store settings (singleton)
- **`POST /v1/settings/store`** — Create the initial store row when none exists (**201**). Returns **409** if settings were already created; use **PUT** to change them.
- **`PUT /v1/settings/store`** — Update existing store fields (partial body allowed).
- **`GET /v1/settings/store`** — Read current store profile.

## Payment settings (singleton)
- **`POST /v1/settings/payments`** — Create initial payment settings when none exist (**201**). Returns **409** if already present; use **PUT** to update.
- **`PUT /v1/settings/payments`** — Update tax, delivery fee, and free-delivery threshold.
- **`GET /v1/settings/payments`** — Read current payment settings.

## Business hours
- **`PUT /v1/settings/business-hours`** — Send `{ "hours": [ { "day", "open_time", "close_time" }, … ] }`. Use the same `open_time` and `close_time` for a closed day.

## Menu item images
- Create/update with **`POST /v1/menu-items`** and **`PUT /v1/menu-items/{id}`** using **`multipart/form-data`**.
- Include image in the same request using file field **`image`**.
- For `sizes`, send a JSON array string (e.g. `[{"size":"small","price":10.99,"is_default":false}]`).
- `image_url` is returned in responses and served from **`MEDIA_URL_PREFIX`**.
"""

OPENAPI_TAGS_METADATA = [
    {"name": "auth", "description": "Admin login, refresh token, profile, logout, and change password."},
    {"name": "dashboard", "description": "Summary KPIs and overview widgets."},
    {"name": "orders", "description": "Order lifecycle, search, status updates, and line items."},
    {
        "name": "menu-items",
        "description": "Menu products, sizes, and pricing. Create/update accept multipart with optional `image` upload; `image_url` in responses is the public URL.",
    },
    {"name": "categories", "description": "Categories and subcategories for the menu."},
    {"name": "toppings", "description": "Toppings catalog and availability."},
    {"name": "crusts", "description": "Crust types and options."},
    {"name": "inventory", "description": "Stock levels, SKUs, and inventory movement logs."},
    {"name": "customers", "description": "Customer records, search, and loyalty points."},
    {"name": "employees", "description": "Staff accounts, schedules, and status."},
    {"name": "roles", "description": "RBAC roles and permission sets."},
    {
        "name": "settings",
        "description": "Store profile (GET/POST/PUT store), business hours, payments/tax, and notification toggles.",
    },
    {"name": "reports", "description": "Report generation and exports."},
    {"name": "health", "description": "Liveness probe; no authentication required."},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.media_root).resolve().joinpath("menu_items").mkdir(parents=True, exist_ok=True)
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    except Exception:
        log.error("Startup failed (database URL / MySQL / permissions). Details:\n%s", traceback.format_exc())
        raise
    yield


app = FastAPI(
    title="PizzaHub POS API",
    summary="POS admin backend for PizzaHub.",
    description=API_DESCRIPTION,
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "PizzaHub API"},
    license_info={"name": "Proprietary"},
    servers=[
        {
            "url": "/",
            "description": "Current host (paths already include `/v1/...`).",
        },
    ],
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 4,
        "syntaxHighlight.theme": "monokai",
    },
)

origins = (
    [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if settings.cors_origins != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

v1_prefix = "/v1"
app.include_router(auth.router, prefix=v1_prefix)
app.include_router(dashboard.router, prefix=v1_prefix)
app.include_router(orders.router, prefix=v1_prefix)
app.include_router(menu_items.router, prefix=v1_prefix)
app.include_router(categories.router, prefix=v1_prefix)
app.include_router(toppings.router, prefix=v1_prefix)
app.include_router(crusts.router, prefix=v1_prefix)
app.include_router(inventory.router, prefix=v1_prefix)
app.include_router(customers.router, prefix=v1_prefix)
app.include_router(employees.router, prefix=v1_prefix)
app.include_router(roles.router, prefix=v1_prefix)
app.include_router(settings_router.router, prefix=v1_prefix)
app.include_router(reports.router, prefix=v1_prefix)

_menu_media_dir = Path(settings.media_root).resolve() / "menu_items"
_menu_media_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.media_url_prefix.rstrip("/"),
    StaticFiles(directory=str(_menu_media_dir)),
    name="menu_item_media",
)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
