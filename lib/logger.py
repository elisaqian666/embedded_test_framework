"""Scoped console and file logging without changing the application's root logger."""

import copy
import logging
import sys
import uuid
from collections.abc import Iterable
from typing import Self

from embedded_framework.configurator.configuration import LoggingConfig

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DIRECT_ENGINE_NAMES = {
    "ssh": "ssh_engine",
    "ftp": "ftp_engine",
    "serial": "serial_engine",
    "socket": "socket_engine",
    "websocket": "websocket_engine",
}
_ENGINE_DISPLAY_NAMES = frozenset(_DIRECT_ENGINE_NAMES.values()) | {"http_engine"}


class DisplayNameFilter(logging.Filter):
    """Display stable category names without changing the source loggers."""

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        if name == "paramiko" or name.startswith("paramiko."):
            record.name = "ssh_engine"
        elif name in _DIRECT_ENGINE_NAMES:
            record.name = _DIRECT_ENGINE_NAMES[name]
        elif name.startswith("embedded_framework.runtime."):
            category = name.rsplit(".", 1)[-1]
            record.name = category if category in _ENGINE_DISPLAY_NAMES else "setup"
        elif name.startswith("embedded_framework.helpers."):
            record.name = "helper"
        return True


def configure_root_logging(level: int | str = logging.INFO, *, stream: object | None = None) -> None:
    """Apply the standard timestamp/level/logger format to the process root logger."""
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=stream, force=True)
    for handler in logging.getLogger().handlers:
        handler.addFilter(DisplayNameFilter())


class RedactingFormatter(logging.Formatter):
    """Format a record copy and mask configured secret values, including traceback text."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__(LOG_FORMAT)
        self._secrets = sorted({value for value in secrets if isinstance(value, str) and value}, key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        """Preserve the original record for other handlers."""
        result = super().format(copy.copy(record))
        for secret in self._secrets:
            result = result.replace(secret, "********")
        return result


class LoggingSession:
    """Own handlers for one runtime; separate runtimes cannot duplicate each other's output."""

    def __init__(self, config: LoggingConfig, *, secrets: Iterable[str] = ()) -> None:
        configure_root_logging(config.level)
        self.logger = logging.getLogger(f"embedded_framework.runtime.{uuid.uuid4().hex}")
        self.logger.setLevel(config.level)
        self.logger.propagate = False
        formatter = RedactingFormatter(secrets)
        self._handlers: list[logging.Handler] = []
        try:
            if config.console:
                self._handlers.append(logging.StreamHandler(sys.stderr))
            if config.file:
                config.file.parent.mkdir(parents=True, exist_ok=True)
                self._handlers.append(logging.FileHandler(config.file, encoding="utf-8"))
            if not self._handlers:
                self._handlers.append(logging.NullHandler())
            for handler in self._handlers:
                handler.setFormatter(formatter)
                handler.addFilter(DisplayNameFilter())
                self.logger.addHandler(handler)
        except BaseException as error:
            try:
                self.close()
            except Exception as cleanup_error:  # noqa: BLE001 - retain the original logging setup error
                error.add_note(f"Logging cleanup also failed: {type(cleanup_error).__name__}")
            raise

    def close(self) -> None:
        """Release only this session's handlers; repeated calls are harmless."""
        errors = []
        for handler in list(self._handlers):
            self.logger.removeHandler(handler)
            try:
                handler.close()
            except Exception as error:  # noqa: BLE001 - close all owned handlers before reporting errors
                errors.append(error)
            else:
                self._handlers.remove(handler)
        if errors:
            message = "Unable to close logging handlers"
            raise ExceptionGroup(message, errors)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
