import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.bootstrap import seed_if_empty
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
from app.utils.responses import err

log = logging.getLogger("uvicorn.error")


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
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
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


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and exc.detail.get("success") is False:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    details: dict = {}
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x != "body")
        msg = e.get("msg", "")
        details.setdefault(loc or "request", []).append(msg)
    return JSONResponse(
        status_code=422,
        content=err("VALIDATION_ERROR", "The given data was invalid.", details=details),
    )


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


@app.get("/health")
def health():
    return {"status": "ok"}
