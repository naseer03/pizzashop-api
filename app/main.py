import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

## Authentication
1. Call **`POST /v1/auth/login`** with email and password.
2. Copy `data.access_token` from the response.
3. Click **Authorize** in Swagger UI, enter `Bearer <token>` or paste the token (Swagger adds `Bearer` if you use the lock flow).
4. Protected routes require a valid JWT access token.

## Response shape
Successful responses wrap payloads as `{ "success": true, "data": ... }`.
Errors use `{ "success": false, "error": { "code", "message", ... } }` with appropriate HTTP status codes.
"""

OPENAPI_TAGS_METADATA = [
    {"name": "auth", "description": "Admin login, token refresh, profile, and password."},
    {"name": "dashboard", "description": "Summary KPIs and overview widgets."},
    {"name": "orders", "description": "Order lifecycle, search, and updates."},
    {"name": "menu-items", "description": "Menu products, sizes, and pricing."},
    {"name": "categories", "description": "Categories and subcategories."},
    {"name": "toppings", "description": "Toppings catalog."},
    {"name": "crusts", "description": "Crust types and options."},
    {"name": "inventory", "description": "Stock, SKUs, and inventory movements."},
    {"name": "customers", "description": "Customer records and loyalty."},
    {"name": "employees", "description": "Staff, roles on shift, and schedules."},
    {"name": "roles", "description": "RBAC roles and permissions."},
    {"name": "settings", "description": "Store profile, business hours, payments, and notifications."},
    {"name": "reports", "description": "Exports and reporting."},
    {"name": "health", "description": "Liveness probe (no auth)."},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
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
    description=API_DESCRIPTION,
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
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


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
