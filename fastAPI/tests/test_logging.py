import json
import logging

from src.core.logging import JsonFormatter


def test_json_logging_preserves_exception_details() -> None:
    try:
        raise RuntimeError("Copilot authentication check failed")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1,
            "Copilot startup failed", (), sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "Copilot startup failed"
    assert "RuntimeError: Copilot authentication check failed" in payload["exception"]


def test_normal_json_logging_has_no_exception_field() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "Ready", (), None)
    assert "exception" not in json.loads(JsonFormatter().format(record))
