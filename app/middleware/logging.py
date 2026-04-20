"""
Request-ID middleware + structured JSON logging setup.

Every request gets a UUID injected as X-Request-ID (echoed in the response).
In production the root logger emits JSON; in dev it keeps the human-readable format.
"""
import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable so any log call during a request can include the request ID
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line — friendly for CloudWatch / Datadog."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Call once at startup. json_logs=True in production."""
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler()
        root.addHandler(handler)

    handler = root.handlers[0]
    handler.addFilter(_RequestIdFilter())

    if json_logs:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    - Reads X-Request-ID from incoming request (or generates one).
    - Sets the context var so log records include it.
    - Echoes it back in the response header.
    - Logs a structured access line at INFO with method, path, status, and latency.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_var.set(req_id)
        log = logging.getLogger("mdm.access")

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            log.info(
                "%s %s %s %.1fms",
                request.method,
                request.url.path,
                getattr(response, "status_code", "???"),
                latency_ms,
            )
            _request_id_var.reset(token)

        response.headers["X-Request-ID"] = req_id
        return response
