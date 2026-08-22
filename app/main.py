import os

# Must run before crewai is imported anywhere in the dependency chain below —
# otherwise it tries to phone home to telemetry.crewai.com at import/execution
# time, adding an unnecessary external dependency to startup/request reliability
# (and sending data to a third party without explicit opt-in).
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes_chat import router as chat_router
from app.api.v1.routes_health import router as health_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="Personal Assistant", version="0.1.0")

    # Middleware order matters: Starlette wraps the LAST-added middleware as
    # OUTERMOST. CORS must be outermost so its headers land on every response,
    # including ones BodySizeLimitMiddleware rejects before reaching the route
    # — otherwise the browser discards the error body as a cross-origin
    # failure instead of surfacing the actual 413. Add in inner-to-outer order.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(chat_router, prefix="/api/v1")

    return app


app = create_app()
