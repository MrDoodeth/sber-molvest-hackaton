from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class ForbiddenError(AppError):
    def __init__(self, message: str = "Недостаточно прав") -> None:
        super().__init__(403, "forbidden", message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Ресурс не найден") -> None:
        super().__init__(404, "not_found", message)


class ConflictError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(409, "conflict", message, details)


class UnprocessableError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(422, "unprocessable", message, details)


class ServiceUnavailableError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(503, "service_unavailable", message, details)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            body["details"] = exc.details
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(body),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(
                {
                    "code": "validation_error",
                    "message": "Некорректные данные запроса",
                    "details": exc.errors(),
                }
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": "http_error",
                "message": str(exc.detail),
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled API error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Внутренняя ошибка сервера",
            },
        )
