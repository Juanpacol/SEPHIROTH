"""Structured logging — stdlib only, key=value lines that grep/parse cleanly.

Example output:
    2026-07-06T17:41:43Z level=INFO logger=api.request request_id=1f3a…
    method=POST path=/api/agents/consult status=200 duration_ms=171904

Inside a consultation every line also carries `trace_id=…` (right after the
logger), so one consultation's lines -- including each model call and any
fallback -- can be pulled out of a mixed log with a single search.
"""

from __future__ import annotations

import logging
import sys

from sephiroth.telemetry.context import current_trace_id


class KeyValueFormatter(logging.Formatter):
    """`timestamp level=… logger=… [trace_id=…] <message>` — messages are
    key=value pairs; `trace_id` appears only inside a consultation."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ")
        trace_id = current_trace_id()
        trace = f" trace_id={trace_id}" if trace_id else ""
        base = f"{timestamp} level={record.levelname} logger={record.name}{trace} {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def _log_uncaught(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("api.fatal").critical("uncaught exception", exc_info=(exc_type, exc, tb))
    for stream in (sys.stdout, sys.stderr):
        stream.flush()


def setup_logging(debug: bool = False) -> None:
    """Configure the root logger once; idempotent across uvicorn reloads."""
    root = logging.getLogger()
    if any(getattr(h, "_clinical_ai", False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())
    handler._clinical_ai = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Keep noisy third-party loggers at WARNING.
    for name in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)

    sys.excepthook = _log_uncaught
    logging.captureWarnings(True)
