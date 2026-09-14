import io
import json
import logging
import importlib

import pytest

from embedded_test_framework import Device, configure_logging, get_logger, load_device, load_logging_config, ConfigurationError
from embedded_test_framework.engine import MemoryTransport, CommandResult
from embedded_test_framework.dut.services import SystemService


@pytest.fixture(autouse=True)
def restore_logging():
    module = importlib.import_module("embedded_test_framework.libs.logging")
    loggers = [logging.getLogger("embedded_test_framework")] + [get_logger(c) for c in ("engine", "server", "dut", "host")]
    states = [(l, l.level, l.propagate, l.handlers[:]) for l in loggers]
    previous = module._handler
    yield
    if module._handler is not None and module._handler is not previous:
        module._handler.close()
    for logger, level, propagate, handlers in states:
        logger.setLevel(level)
        logger.propagate = propagate
        logger.handlers[:] = handlers
    module._handler = previous


@pytest.mark.parametrize("level,count", [("debug", 4), ("info", 3), ("warning", 2), ("error", 1)])
def test_level_filtering(level, count):
    stream = io.StringIO()
    configure_logging({"level": level}, stream=stream)
    logger = get_logger("engine", "SSH")
    for value in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
        logger.log(value, "event")
    assert len(stream.getvalue().splitlines()) == count
    assert "[engine] [SSH]" in stream.getvalue()


def test_overrides_reset_and_no_duplicate_handlers():
    stream = io.StringIO()
    root = logging.getLogger()
    state = (root.level, root.handlers[:])
    configure_logging({"level": "error", "levels": {"engine": "debug"}}, stream=stream)
    get_logger("engine").debug("visible")
    get_logger("host").info("hidden")
    configure_logging({"level": "info"}, stream=stream)
    get_logger("engine").debug("also-hidden")
    get_logger("host").info("once")
    assert stream.getvalue().count("once") == 1
    assert "hidden" not in stream.getvalue()
    assert (root.level, root.handlers) == state


@pytest.mark.parametrize("config", [{"level": "trace"}, {"level": 10}, {"levels": {"typo": "info"}}, {"levels": []}, {"typo": "info"}])
def test_invalid_config(config):
    with pytest.raises(ConfigurationError):
        configure_logging(config)


def test_categories_and_sensitive_data():
    stream = io.StringIO()
    configure_logging({"level": "debug"}, stream=stream)
    with Device("board", {"shell": MemoryTransport({"secret-command": "secret-response", "bad": CommandResult("bad", exit_code=1)})}) as device:
        assert SystemService(device).version("secret-command") == "secret-response"
        device.execute("bad")
        get_logger("host", "bench").info("host ready")
        with pytest.raises(Exception):
            device.execute("secret-missing-command")
    output = stream.getvalue()
    assert all(f"[{category}]" in output for category in ("engine", "server", "dut", "host"))
    assert "secret" not in output
    assert "WARNING" in output and "ERROR" in output


def test_inventory_and_standalone_config(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"logging": {"level": "error"}, "devices": {"dut": {"channels": {"shell": {"type": "memory"}}}}}), encoding="utf-8")
    load_device(path)
    assert get_logger("engine").getEffectiveLevel() == logging.ERROR
    path.write_text('{"logging": {"level": "debug"}}', encoding="utf-8")
    load_logging_config(path)
    assert get_logger("host").getEffectiveLevel() == logging.DEBUG
