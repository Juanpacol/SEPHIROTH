"""Structured logging — stdlib only, key=value lines that grep/parse cleanly.

Example output:
    2026-07-06T17:41:43Z level=INFO logger=api.request request_id=1f3a…
    method=POST path=/api/agents/consult status=200 duration_ms=171904
"""

from __future__ import annotations

import logging
import sys


class KeyValueFormatter(logging.Formatter):
    """`timestamp level=… logger=… <message>` — messages are key=value pairs."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ")
        base = f"{timestamp} level={record.levelname} logger={record.name} {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


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
