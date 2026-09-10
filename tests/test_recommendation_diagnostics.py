import logging

from scripts.check_recommendations import SafeWarnings


def test_diagnostics_do_not_expose_exception_content():
    handler = SafeWarnings()
    error = ValueError("private content must never be printed")
    record = logging.LogRecord("test", logging.WARNING, "", 1, "OpenRouter recommendation fallback: %s", (error,), (ValueError, error, None))
    handler.emit(record)
    assert handler.reason == {"type": "ValueError", "status": None}
    handler.emit(logging.LogRecord("test", logging.WARNING, "", 1, "OpenRouter recommendation fallback: API key is not configured", (), None))
    assert handler.reason == {"type": "missing_key"}
