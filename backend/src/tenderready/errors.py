"""Stable API errors without submitted secrets, database SQL, or tracebacks."""
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


def error_response(status: int, code: str, message: str, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or []}},
        headers=headers,
    )


def install_error_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        codes = {
            401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
            409: "conflict", 413: "file_too_large", 415: "unsupported_file_type", 422: "validation_error", 503: "service_unavailable",
        }
        # Only explicit application messages or framework HTTP labels reach here.
        return error_response(exc.status_code, codes.get(exc.status_code, "request_error"),
                              str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Do not echo `input`, `ctx`, or arbitrary exception text from validators.
        details = [{"field": ".".join(str(part) for part in e["loc"]), "type": e["type"]}
                   for e in exc.errors()]
        return error_response(422, "validation_error", "Request validation failed.", details)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, __: IntegrityError):
        return error_response(409, "conflict", "The operation conflicts with stored data constraints.")

    @app.exception_handler(OperationalError)
    async def database_unavailable(_: Request, __: OperationalError):
        return error_response(503, "database_unavailable", "Database unavailable or migrations not applied.")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed: %s", type(exc).__name__)
        return error_response(500, "database_error", "The database operation could not be completed.")

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        logger.error("Request failed: %s", type(exc).__name__)
        return error_response(500, "internal_error", "An unexpected error occurred.")
