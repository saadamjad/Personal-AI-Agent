import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.errors import error_body
from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = str(uuid.uuid4())
        token = request_id_ctx.set(req_id)
        try:
            start = time.monotonic()
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            response.headers["X-Request-ID"] = req_id
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            request_id_ctx.reset(token)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > settings.chat_max_body_bytes:
            return JSONResponse(
                status_code=413,
                content=error_body("Request body exceeds the allowed size."),
            )
        return await call_next(request)
