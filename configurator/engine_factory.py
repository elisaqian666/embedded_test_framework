"""Lazy protocol factories for configuration-driven initialization."""

import importlib
import inspect
import logging
import math
import socket
from collections.abc import Callable, Mapping
from typing import Any

from embedded_framework.configurator.configuration import ConfigurationError, ConnectionConfig

_FACTORIES = {
    "ssh": ("sshengine", "make_ssh_engine"),
    "serial": ("serialengine", "make_serial_engine"),
    "socket": ("socket_engine", "make_socket_engine"),
    "tcp": ("socket_engine", "make_socket_engine"),
    "udp": ("socket_engine", "make_socket_engine"),
    "ftp": ("ftpengine", "make_ftp_engine"),
    "ftps": ("ftpengine", "make_ftp_engine"),
    "http": ("httpengine", "make_http_engine"),
    "https": ("httpengine", "make_http_engine"),
    "websocket": ("websocket_engine", "make_websocket_engine"),
}
_HTTP_AUTH_FIELDS = 2
_ENGINE_LOGGER_NAMES = {
    "ssh": "ssh_engine",
    "serial": "serial_engine",
    "socket": "socket_engine",
    "tcp": "socket_engine",
    "udp": "socket_engine",
    "ftp": "ftp_engine",
    "ftps": "ftp_engine",
    "http": "http_engine",
    "https": "http_engine",
    "websocket": "websocket_engine",
}


class EngineFactory:
    """Load configured protocols only; injected factories allow additional transports.

    A factory accepts keyword options and returns an engine with ``close()``.
    Instances own their registries; no global connection cache is used.
    """

    def __init__(self, factories: Mapping[str, Callable[..., Any]] | None = None) -> None:
        self._factories = dict(factories or {})

    def _resolve(self, connection: ConnectionConfig) -> tuple[Callable[..., Any], dict[str, Any]]:
        protocol = connection.protocol
        options = dict(connection.options)
        if protocol in self._factories:
            return self._factories[protocol], options
        if protocol not in _FACTORIES:
            message = f"Unsupported communication protocol: {protocol}"
            raise ConfigurationError(message)
        module, name = _FACTORIES[protocol]
        factory = getattr(importlib.import_module(f"embedded_framework.communication.{module}"), name)
        if protocol in {"tcp", "udp"}:
            options["s_type"] = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
        if protocol == "ftps":
            options["protocol"] = "ftps"
        if protocol == "https" and not str(options.get("base_url", "")).startswith("https://"):
            message = "https connections require an https:// base_url"
            raise ConfigurationError(message)
        if protocol in {"http", "https"} and isinstance(options.get("auth"), list):
            if len(options["auth"]) != _HTTP_AUTH_FIELDS:
                message = "HTTP auth must contain username and password"
                raise ConfigurationError(message)
            options["auth"] = tuple(options["auth"])
        return factory, options

    def validate(self, connection: ConnectionConfig) -> None:
        """Check factory arguments before any device connection is opened."""
        factory, options = self._resolve(connection)
        try:
            inspect.signature(factory).bind(**options)
            # HTTP exposes **kwargs at its maker; validate the actual constructor too.
            if connection.protocol in {"http", "https"} and connection.protocol not in self._factories:
                engine_type = importlib.import_module("embedded_framework.communication.httpengine").HttpEngine
                inspect.signature(engine_type).bind(**options)
        except TypeError:
            message = f"Invalid or missing factory options for protocol: {connection.protocol}"
            raise ConfigurationError(message) from None
        if connection.protocol not in self._factories:
            self._validate_options(options)

    @staticmethod
    def _validate_options(options: dict[str, Any]) -> None:
        for name in ("timeout", "s_timeout", "read_timeout", "write_timeout"):
            if name not in options:
                continue
            value = options[name]
            minimum_inclusive = name in {"read_timeout", "write_timeout"}
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or (value < 0 if minimum_inclusive else value <= 0)
            ):
                message = f"{name} must be a finite {'non-negative' if minimum_inclusive else 'positive'} number"
                raise ConfigurationError(message)
        for name in ("host", "hostname", "address", "com_port", "username", "url", "base_url"):
            if name in options and (not isinstance(options[name], str) or not options[name]):
                message = f"{name} must be a non-empty string"
                raise ConfigurationError(message)
        for name, minimum, maximum in (("port", 1, 65535), ("baudrate", 1, None), ("retry", 0, None)):
            value = options.get(name)
            if name in options and (type(value) is not int or value < minimum or (maximum is not None and value > maximum)):
                message = f"Invalid integer option: {name}"
                raise ConfigurationError(message)

    def create(self, connection: ConnectionConfig, *, logger: logging.Logger | None = None) -> Any:
        """Construct an engine; open serial ports and close them if opening fails."""
        self.validate(connection)
        factory, options = self._resolve(connection)
        engine = factory(**options)
        if not callable(getattr(engine, "close", None)):
            message = "Engine factories must return an object with close()"
            raise TypeError(message)
        try:
            if logger is not None and hasattr(engine, "logger"):
                engine.logger = logger.getChild(_ENGINE_LOGGER_NAMES.get(connection.protocol, "engine"))
            if connection.protocol == "serial":
                engine.open_serial_connection()
        except BaseException as error:
            try:
                engine.close()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve the original initialization error
                error.add_note(f"Engine cleanup also failed: {type(cleanup_error).__name__}")
            raise
        return engine
