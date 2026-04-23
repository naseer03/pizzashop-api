"""Central FastAPI exception handlers for consistent JSON errors and correct status codes."""

from __future__ import annotations

import logging
import re
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError, NoResultFound, OperationalError, SQLAlchemyError

from app.utils.responses import err

log = logging.getLogger("uvicorn.error")


def _http_error_payload(exc: StarletteHTTPException) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("success") is False:
        return detail
    if isinstance(detail, dict) and "error" in detail and isinstance(detail["error"], dict):
        return {"success": False, **detail} if "success" not in detail else detail
    if isinstance(detail, dict):
        return detail
    message = str(detail) if detail is not None else "Request could not be completed."
    code = f"HTTP_{exc.status_code}"
    return err(code, message)


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_http_error_payload(exc))


async def request_validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details: dict[str, list[str]] = {}
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x != "body")
        msg = e.get("msg", "")
        details.setdefault(loc or "request", []).append(msg)
    return JSONResponse(
        status_code=422,
        content=err("VALIDATION_ERROR", "The given data was invalid.", details=details),
    )


async def pydantic_validation_exception_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=err(
            "VALIDATION_ERROR",
            "The given data was invalid.",
            details={"errors": exc.errors(include_url=False)},
        ),
    )


def _integrity_user_message(orig: Any) -> tuple[str, dict[str, Any] | None]:
    """Map MySQL / DB integrity failures to stable API messages."""
    text = str(orig) if orig is not None else ""
    lower = text.lower()
    extra: dict[str, Any] | None = None

    if "1062" in text or "duplicate entry" in lower:
        m = re.search(r"Duplicate entry '([^']*)'", text)
        if m:
            extra = {"field_hint": m.group(1)}
        return "A record with this value already exists.", extra

    if "1451" in text or "cannot delete" in lower or ("cannot update" in lower and "foreign key" in lower):
        return "This record is still referenced by other data and cannot be removed or updated in this way.", None

    if "1452" in text or "foreign key constraint fails" in lower:
        return "A referenced record does not exist, or the link is invalid.", None

    if "1048" in text or "column" in lower and "cannot be null" in lower:
        return "A required value was missing.", None

    return "The operation conflicts with existing data.", None


async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    message, details = _integrity_user_message(getattr(exc, "orig", None))
    log.warning("IntegrityError: %s", exc, exc_info=True)
    body = err("RESOURCE_CONFLICT", message, details=details)
    return JSONResponse(status_code=409, content=body)


def _mysql_errno_from_operational(exc: OperationalError) -> int | None:
    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "args", None) and len(orig.args) >= 1:
        try:
            return int(orig.args[0])
        except (TypeError, ValueError):
            return None
    return None


async def operational_error_handler(_: Request, exc: OperationalError) -> JSONResponse:
    log.error("Database operational error: %s", exc, exc_info=True)
    errno = _mysql_errno_from_operational(exc)
    # PyMySQL maps some server errors to OperationalError; schema drift is not "DB down".
    if errno in (1054, 1146):
        orig = getattr(exc, "orig", None)
        hint = str(orig.args[1]) if orig is not None and len(orig.args) > 1 else str(exc)
        return JSONResponse(
            status_code=500,
            content=err(
                "DATABASE_SCHEMA_MISMATCH",
                "The database schema does not match this API version (missing table or column). "
                "Apply the SQL migrations for this project or recreate tables, then try again.",
                details={"mysql_errno": errno, "hint": hint},
            ),
        )
    return JSONResponse(
        status_code=503,
        content=err(
            "DATABASE_UNAVAILABLE",
            "The database is temporarily unavailable. Please try again shortly.",
        ),
    )


async def no_result_found_handler(_: Request, exc: NoResultFound) -> JSONResponse:
    log.info("NoResultFound: %s", exc)
    return JSONResponse(
        status_code=404,
        content=err("RESOURCE_NOT_FOUND", "The requested resource was not found."),
    )


async def data_error_handler(_: Request, exc: DataError) -> JSONResponse:
    log.warning("DataError: %s", exc, exc_info=True)
    orig = getattr(exc, "orig", None)
    details = {"hint": str(orig)} if orig is not None else None
    return JSONResponse(
        status_code=400,
        content=err(
            "INVALID_DATA",
            "One or more values are not valid for the database column or type.",
            details=details,
        ),
    )


async def sqlalchemy_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    log.error("SQLAlchemyError: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=err(
            "DATABASE_ERROR",
            "A database error occurred while processing your request.",
        ),
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    log.error("Unhandled exception: %s", exc, exc_info=True)
    log.debug("Traceback:\n%s", traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content=err(
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again or contact support if the problem persists.",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    # FastAPI raises fastapi.exceptions.HTTPException; some Starlette paths raise the base class.
    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, operational_error_handler)
    app.add_exception_handler(NoResultFound, no_result_found_handler)
    app.add_exception_handler(DataError, data_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
