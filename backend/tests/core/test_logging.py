import logging

from app.core.logging import DropQueryString


def test_access_log_drops_query_string_with_names() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/api/v1/persons?q=K%C3%B6hler", "1.1", 200),
        None,
    )

    assert DropQueryString().filter(record) is True
    assert "hler" not in record.getMessage()
    assert "/api/v1/persons " in record.getMessage()
