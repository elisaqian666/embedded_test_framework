"""Package-scoped console logging; never configures the root logger."""
from functools import wraps
import json
import logging
from pathlib import Path
import threading

_CATEGORIES = ("engine", "server", "dut", "host")
_lock = threading.RLock()
_handler = None


def get_logger(category, name=None):
    from .errors import ConfigurationError
    if category not in _CATEGORIES:
        raise ConfigurationError("Logger category must be engine, server, dut or host")
    return logging.getLogger(".".join(filter(None, ("embedded_test_framework", category, name))))


def _level(value):
    from .errors import ConfigurationError
    if not isinstance(value, str) or value.lower() not in ("info", "error", "warning", "debug"):
        raise ConfigurationError("Log level must be info, error, warning or debug")
    return getattr(logging, value.upper())


class _Formatter(logging.Formatter):
    def format(self, record):
        copy = logging.makeLogRecord(record.__dict__.copy())
        parts = copy.name.split(".", 2)
        copy.category = parts[1] if len(parts) > 1 else "framework"
        copy.component = parts[2] if len(parts) > 2 else "-"
        return super().format(copy)


def configure_logging(config=None, *, stream=None):
    """Replace our console handler; last explicit config wins process-wide."""
    from .errors import ConfigurationError
    global _handler
    config = {} if config is None else config
    if not isinstance(config, dict) or set(config) - {"level", "levels"}:
        raise ConfigurationError("logging accepts only level and levels")
    default = _level(config.get("level", "info"))
    overrides = config.get("levels", {})
    if not isinstance(overrides, dict) or set(overrides) - set(_CATEGORIES):
        raise ConfigurationError("logging.levels accepts engine, server, dut and host")
    levels = {category: _level(value) for category, value in overrides.items()}
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_Formatter("%(asctime)s %(levelname)-7s [%(category)s] [%(component)s] %(message)s",
                                    datefmt="%Y-%m-%d %H:%M:%S"))
    with _lock:
        logger = logging.getLogger("embedded_test_framework")
        if _handler is not None:
            logger.removeHandler(_handler)
            _handler.close()
        logger.setLevel(default)
        logger.propagate = False
        for category in _CATEGORIES:
            get_logger(category).setLevel(levels.get(category, logging.NOTSET))
        logger.addHandler(handler)
        _handler = handler


def load_logging_config(path):
    from .errors import ConfigurationError
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError("Cannot read logging configuration JSON") from exc
    if not isinstance(document, dict) or "logging" not in document:
        raise ConfigurationError("Configuration requires a logging object")
    configure_logging(document["logging"])


def log_operation(method):
    """Log metadata only, excluding arguments, response bodies and exception text."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        self.logger.debug("%s started", method.__name__)
        try:
            result = method(self, *args, **kwargs)
        except Exception as exc:
            self.logger.error("%s failed (%s, code=%s)", method.__name__, type(exc).__name__,
                              getattr(exc, "code", "UNEXPECTED_ERROR"))
            raise
        if getattr(result, "ok", None) is False:
            self.logger.warning("%s completed with an unsuccessful result", method.__name__)
        else:
            self.logger.info("%s completed", method.__name__)
        return result
    return wrapped
