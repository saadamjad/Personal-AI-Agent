from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for errors that should surface a safe, specific message to the client."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "APP_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ValidationAppError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_REQUEST"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"


class RequestTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "REQUEST_TOO_LARGE"


class FlowExecutionError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "AGENT_UNAVAILABLE"


def _error_body(code: str, message: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "request_id": request_id_ctx.get()}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", "Something went wrong. Please try again."),
        )
