import io
import logging

import pytest

from embedded_test_framework.lib.logging_extras import LogHandler


@pytest.mark.parametrize(
    "message,args,expected",
    [
        ("first line\nsecond %s", ("line",), "first line\nsecond line"),
        ("output: %s", ("first\nsecond\n100% ready",), "output: first\nsecond\n100% ready"),
        ("device=%(device)s progress=%(progress)s%%", {"device": "board", "progress": 50}, "device=board progress=50%"),
        ("literal 100% and %s", (), "literal 100% and %s"),
    ],
)
def test_console_handler_preserves_record_and_full_message_for_other_handlers(message, args, expected):
    console, file = io.StringIO(), io.StringIO()
    logger = logging.Logger("regression", logging.INFO)
    logger.addHandler(LogHandler(console))
    logger.addHandler(logging.StreamHandler(file))
    record = logger.makeRecord("regression", logging.INFO, __file__, 1, message, args, None)
    original_message, original_args = record.msg, record.args
    logger.handle(record)
    assert expected in console.getvalue()
    assert expected in file.getvalue()
    assert record.msg == original_message
    assert record.args == original_args


def test_exception_and_exception_group_are_preserved_by_console_handler():
    console, file = io.StringIO(), io.StringIO()
    logger = logging.Logger("trace-regression", logging.INFO)
    logger.addHandler(LogHandler(console))
    logger.addHandler(logging.StreamHandler(file))
    try:
        try:
            raise ValueError("device failure")
        except ValueError as error:
            raise ExceptionGroup("cleanup failed", [error]) from error
    except ExceptionGroup:
        logger.exception("request %s failed\nretaining traceback", "read")
    for output in (console.getvalue(), file.getvalue()):
        assert "request read failed" in output
        assert "retaining traceback" in output
        assert "ValueError: device failure" in output
        assert "ExceptionGroup: cleanup failed" in output
