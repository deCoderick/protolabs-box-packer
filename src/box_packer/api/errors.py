"""Every error response uses the ErrorResponse envelope: {code, message, details}."""

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from box_packer.api.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Sequence[ErrorDetail] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = list(details)


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Sequence[ErrorDetail] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=list(details))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        details = [_detail_from_pydantic(error) for error in errors]
        if any(error["type"] == "json_invalid" for error in errors):
            return error_response(
                HTTPStatus.BAD_REQUEST, "invalid_json", "Request body is not valid JSON.", details
            )
        return error_response(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation_error",
            "Request body failed validation.",
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = HTTPStatus(exc.status_code)
        return error_response(
            status,
            status.phrase.lower().replace(" ", "_"),
            str(exc.detail),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "An unexpected error occurred."
        )


def _detail_from_pydantic(error: Mapping[str, Any]) -> ErrorDetail:
    loc = list(error["loc"])
    if loc and loc[0] == "body":
        loc = loc[1:]
    message = error["msg"]
    if error["type"] == "json_invalid" and (reason := error.get("ctx", {}).get("error")):
        message = f"{message}: {reason}"
    return ErrorDetail(loc=loc, type=error["type"], message=message)
