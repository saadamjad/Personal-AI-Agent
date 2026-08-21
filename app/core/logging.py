import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_REDACT_KEYS = {"api_key", "openai_api_key", "anthropic_api_key", "authorization", "password"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class _RedactingFormatter(jsonlogger.JsonFormatter):
    def process_log_record(self, log_record: dict[str, object]) -> dict[str, object]:
        for key in list(log_record.keys()):
            if key.lower() in _REDACT_KEYS:
                log_record[key] = "***REDACTED***"
        result: dict[str, object] = super().process_log_record(log_record)  # type: ignore[no-untyped-call]
        return result


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    formatter: logging.Formatter = _RedactingFormatter(  # type: ignore[no-untyped-call]
        "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers at INFO
    for noisy in ("httpx", "chromadb", "LiteLLM"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
