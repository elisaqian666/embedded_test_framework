"""Data-only configuration for generic embedded devices (JSON or TOML)."""

import copy
import importlib
import inspect
import json
import logging
import math
import os
import re
import socket
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from embedded_framework.lib.custom_exception import EmbeddedFrameworkSetupError
from embedded_framework.configurator.config_labels import LOGLEVELS, LOGGERS

_ENVIRONMENT_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigurationError(EmbeddedFrameworkSetupError):
    """Invalid configuration; messages never include option values."""


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        message = f"{location} must be an object with string keys"
        raise ConfigurationError(message)
    return value


def _known_keys(values: dict[str, Any], allowed: set[str], location: str) -> None:
    if unknown := values.keys() - allowed:
        message = f"Unknown keys at {location}: {', '.join(sorted(unknown))}"
        raise ConfigurationError(message)


def _expand_environment(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                message = f"Required environment variable is not set: {name}"
                raise ConfigurationError(message)
            return os.environ[name]

        return _ENVIRONMENT_VARIABLE.sub(replace, value)
    return value


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        result[key] = _merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


@dataclass(frozen=True)
class ConnectionConfig:
    """A protocol and explicit factory options, with credentials hidden from repr."""

    protocol: str
    options: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class DeviceConfig:
    """Named connections and optional user metadata for a device."""

    name: str
    connections: dict[str, ConnectionConfig]
    default_connection: str
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class LoggingConfig:
    """Console/file logging settings; file paths are relative to the config file."""

    level: str = "INFO"
    console: bool = True
    file: Path | None = None


@dataclass(frozen=True)
class OscilloscopeConfig:
    """Optional oscilloscope configuration; host is required only when enabled."""

    model: str
    enable: bool
    host: str | None = None
    port: int = 5555
    timeout: float = 5


@dataclass(frozen=True)
class FrameworkConfig:
    """Validated configuration, without any imported executable config module."""

    devices: dict[str, DeviceConfig]
    logging: LoggingConfig
    oscilloscope: OscilloscopeConfig | None
    source: Path


def _device(name: str, raw: Any) -> DeviceConfig:
    values = _mapping(raw, f"devices.{name}")
    _known_keys(values, {"connections", "default_connection", "metadata"}, f"devices.{name}")
    connections = {}
    for alias, raw_connection in _mapping(values.get("connections", {}), f"devices.{name}.connections").items():
        location = f"devices.{name}.connections.{alias}"
        connection = _mapping(raw_connection, location)
        _known_keys(connection, {"protocol", "options"}, location)
        protocol = connection.get("protocol")
        if not alias or not isinstance(protocol, str) or not protocol:
            message = f"{location} requires a non-empty alias and protocol"
            raise ConfigurationError(message)
        connections[alias] = ConnectionConfig(
            protocol.lower(), copy.deepcopy(_mapping(connection.get("options", {}), location + ".options"))
        )
    if not name or not connections:
        message = "Each device requires a name and at least one connection"
        raise ConfigurationError(message)
    default = values.get("default_connection", next(iter(connections)))
    if not isinstance(default, str) or default not in connections:
        message = f"devices.{name}.default_connection must name a configured connection"
        raise ConfigurationError(message)
    return DeviceConfig(name, connections, default, copy.deepcopy(_mapping(values.get("metadata", {}), f"devices.{name}.metadata")))


def _oscilloscope(raw: Any) -> OscilloscopeConfig:
    values = _mapping(raw, "osciiloscope")
    _known_keys(values, {"model", "enable", "host", "port", "timeout"}, "osciiloscope")
    model, enable = values.get("model"), values.get("enable")
    if not isinstance(model, str) or not model or type(enable) is not bool:
        raise ConfigurationError("osciiloscope requires a non-empty model and boolean enable")
    host = values.get("host")
    if enable and (not isinstance(host, str) or not host):
        raise ConfigurationError("enabled osciiloscope requires a non-empty host")
    port, timeout = values.get("port", 5555), values.get("timeout", 5)
    if (
        type(port) is not int
        or not 1 <= port <= 65535
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ConfigurationError("osciiloscope port must be 1..65535 and timeout must be positive")
    return OscilloscopeConfig(model.lower(), enable, host, port, float(timeout))


def load_mapping(
    raw: dict[str, Any], *, source: str | Path = "embedded_test_config.py", overrides: dict[str, Any] | None = None
) -> FrameworkConfig:
    """Validate a configuration mapping without executing a configuration module."""
    source_path = Path(source).expanduser().resolve()
    values = _expand_environment(_merge(_mapping(raw, "configuration"), _mapping(overrides or {}, "overrides")))
    _known_keys(values, {"devices", "logging", "osciiloscope"}, "configuration")
    devices = {name: _device(name, value) for name, value in _mapping(values.get("devices", {}), "devices").items()}
    logging_values = _mapping(values.get("logging", {}), "logging")
    _known_keys(logging_values, {"level", "console", "file"}, "logging")
    level, console, log_file = logging_values.get("level", "INFO"), logging_values.get("console", True), logging_values.get("file")
    log_levels = {LOGLEVELS.DEBUG, LOGLEVELS.INFO, LOGLEVELS.WARNING, LOGLEVELS.ERROR, LOGLEVELS.CRITICAL}
    if not isinstance(level, str) or level.lower() not in log_levels:
        message = "logging.level must be DEBUG, INFO, WARNING, ERROR or CRITICAL"
        raise ConfigurationError(message)
    if not isinstance(console, bool) or (log_file is not None and (not isinstance(log_file, str) or not log_file)):
        message = "logging.console must be boolean; logging.file must be a non-empty path"
        raise ConfigurationError(message)
    log_path = (source_path.parent / Path(log_file).expanduser()).resolve() if log_file else None
    oscilloscope = _oscilloscope(values["osciiloscope"]) if "osciiloscope" in values else None
    return FrameworkConfig(devices, LoggingConfig(level.upper(), console, log_path), oscilloscope, source_path)


def load_config(path: str | Path, *, overrides: dict[str, Any] | None = None) -> FrameworkConfig:
    """Load JSON or TOML configuration; explicit overrides precede environment substitution.

    :param path: A UTF-8 JSON or TOML file. Python modules are not executed.
    :param overrides: Optional recursively merged values, useful for CI callers.
    :returns: Validated device and logging configuration.
    :raises ConfigurationError: For invalid structure, syntax or missing env vars.
    """
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() not in {".json", ".toml"}:
        message = "Configuration must be a .json or .toml file"
        raise ConfigurationError(message)
    try:
        text = source.read_text(encoding="utf-8-sig")
        raw = json.loads(text) if source.suffix.lower() == ".json" else tomllib.loads(text)
    except (OSError, UnicodeError, ValueError):
        message = f"Unable to read or parse configuration: {source.name}"
        raise ConfigurationError(message) from None
    return load_mapping(raw, source=source, overrides=overrides)


_FACTORIES = {
    "ssh": ("sshengine", "make_ssh_engine"),
    "serial": ("serialengine", "make_serial_engine"),
    "modbus": ("modbusengine", "make_modbus_rtu_engine"),
    "socket": ("socket_engine", "make_socket_engine"),
    "tcp": ("socket_engine", "make_socket_engine"),
    "udp": ("socket_engine", "make_socket_engine"),
    "ftp": ("ftpengine", "make_ftp_engine"),
    "ftps": ("ftpengine", "make_ftp_engine"),
    "http": ("httpengine", "make_http_engine"),
    "https": ("httpengine", "make_http_engine"),
    "websocket": ("websocket_engine", "make_websocket_engine"),
}
_ENGINE_LOGGER_NAMES = {
    "ssh": LOGGERS.SSH_ENGINE,
    "serial": LOGGERS.SERIAL_ENGINE,
    "modbus": LOGGERS.SERIAL_ENGINE,
    "socket": LOGGERS.SOCKET_ENGINE,
    "tcp": LOGGERS.SOCKET_ENGINE,
    "udp": LOGGERS.SOCKET_ENGINE,
    "ftp": LOGGERS.FTP_ENGINE,
    "ftps": LOGGERS.FTP_ENGINE,
    "http": LOGGERS.HTTP_ENGINE,
    "https": LOGGERS.HTTP_ENGINE,
    "websocket": LOGGERS.WEBSOCKET_ENGINE,
}
_HTTP_AUTH_FIELDS = 2


class EngineFactory:
    """Create validated generic protocol engines from connection configuration."""

    def __init__(self, factories: Mapping[str, Callable[..., Any]] | None = None) -> None:
        self._factories = dict(factories or {})

    def _resolve(self, connection: ConnectionConfig) -> tuple[Callable[..., Any], dict[str, Any]]:
        protocol = connection.protocol
        options = dict(connection.options)
        if protocol in self._factories:
            return self._factories[protocol], options
        if protocol not in _FACTORIES:
            raise ConfigurationError(f"Unsupported communication protocol: {protocol}")
        module, name = _FACTORIES[protocol]
        factory = getattr(importlib.import_module(f"embedded_framework.communication.{module}"), name)
        if protocol in {"tcp", "udp"}:
            options["s_type"] = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
        if protocol == "ftps":
            options["protocol"] = "ftps"
        if protocol == "https" and not str(options.get("base_url", "")).startswith("https://"):
            raise ConfigurationError("https connections require an https:// base_url")
        if protocol in {"http", "https"} and isinstance(options.get("auth"), list):
            if len(options["auth"]) != _HTTP_AUTH_FIELDS:
                raise ConfigurationError("HTTP auth must contain username and password")
            options["auth"] = tuple(options["auth"])
        return factory, options

    def validate(self, connection: ConnectionConfig) -> None:
        """Validate factory options before opening a connection."""
        factory, options = self._resolve(connection)
        try:
            inspect.signature(factory).bind(**options)
            if connection.protocol in {"http", "https"} and connection.protocol not in self._factories:
                engine_type = importlib.import_module("embedded_framework.communication.httpengine").HttpEngine
                inspect.signature(engine_type).bind(**options)
        except TypeError:
            raise ConfigurationError(f"Invalid or missing factory options for protocol: {connection.protocol}") from None
        if connection.protocol not in self._factories:
            self._validate_options(options)

    @staticmethod
    def _validate_options(options: dict[str, Any]) -> None:
        if "rs485" in options and type(options["rs485"]) is not bool:
            raise ConfigurationError("rs485 must be boolean")
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
                expectation = "non-negative" if minimum_inclusive else "positive"
                raise ConfigurationError(f"{name} must be a finite {expectation} number")
        for name in ("host", "hostname", "address", "com_port", "username", "url", "base_url"):
            if name in options and (not isinstance(options[name], str) or not options[name]):
                raise ConfigurationError(f"{name} must be a non-empty string")
        for name, minimum, maximum in (("port", 1, 65535), ("baudrate", 1, None), ("retry", 0, None)):
            value = options.get(name)
            if name in options and (type(value) is not int or value < minimum or (maximum is not None and value > maximum)):
                raise ConfigurationError(f"Invalid integer option: {name}")

    def create(self, connection: ConnectionConfig, *, logger: logging.Logger | None = None) -> Any:
        """Create an engine and attach its protocol-specific logger."""
        self.validate(connection)
        factory, options = self._resolve(connection)
        engine = factory(**options)
        if not callable(getattr(engine, "close", None)):
            raise TypeError("Engine factories must return an object with close()")
        try:
            if logger is not None and hasattr(engine, "logger"):
                engine.logger = logger.getChild(_ENGINE_LOGGER_NAMES.get(connection.protocol, "engine"))
            if connection.protocol == "serial":
                engine.open_serial_connection()
        except BaseException as error:
            try:
                engine.close()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve the initialization error
                error.add_note(f"Engine cleanup also failed: {type(cleanup_error).__name__}")
            raise
        return engine
