from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

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


class FlowExecutionError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "AGENT_UNAVAILABLE"


def error_body(message: str) -> dict[str, object]:
    """Client-facing error shape: {"error": "<message>"} — matches what the
    website's chatApi.js expects to parse. The error `code` and request ID
    are not part of this body; they're logged server-side (code via the
    logger call sites) and the request ID travels in the X-Request-ID
    response header instead, so nothing observability-relevant is lost."""
    return {"error": message}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info(
            "app_error",
            extra={"path": request.url.path, "code": exc.code, "message": exc.message},
        )
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.message))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("Something went wrong. Please try again."),
        )
