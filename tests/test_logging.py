"""Tests for the stdlib structured logging setup."""

import logging

from core.logging import KeyValueFormatter, setup_logging


def test_setup_logging_adds_handler_once():
    root = logging.getLogger()
    before = len(root.handlers)
    setup_logging(debug=False)
    setup_logging(debug=False)  # idempotent — should not add a second handler
    added = len(root.handlers) - before
    assert added <= 1


def test_setup_logging_debug_sets_debug_level():
    setup_logging.__globals__  # no-op to keep import used
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_clinical_ai", False):
            root.removeHandler(h)
    setup_logging(debug=True)
    assert root.level == logging.DEBUG


def test_key_value_formatter_includes_level_and_logger_name():
    formatter = KeyValueFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello=%s",
        args=("world",),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "level=INFO" in formatted
    assert "logger=test.logger" in formatted
    assert "hello=world" in formatted
