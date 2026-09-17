"""Data-only configuration for generic embedded devices (JSON or TOML)."""

import copy
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from embedded_framework.lib.custom_exception import EmbeddedFrameworkSetupError

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
class FrameworkConfig:
    """Validated configuration, without any imported executable config module."""

    devices: dict[str, DeviceConfig]
    logging: LoggingConfig
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


def load_mapping(
    raw: dict[str, Any], *, source: str | Path = "embedded_test_config.py", overrides: dict[str, Any] | None = None
) -> FrameworkConfig:
    """Validate a configuration mapping without executing a configuration module."""
    source_path = Path(source).expanduser().resolve()
    values = _expand_environment(_merge(_mapping(raw, "configuration"), _mapping(overrides or {}, "overrides")))
    _known_keys(values, {"devices", "logging"}, "configuration")
    devices = {name: _device(name, value) for name, value in _mapping(values.get("devices", {}), "devices").items()}
    logging_values = _mapping(values.get("logging", {}), "logging")
    _known_keys(logging_values, {"level", "console", "file"}, "logging")
    level, console, log_file = logging_values.get("level", "INFO"), logging_values.get("console", True), logging_values.get("file")
    if not isinstance(level, str) or level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        message = "logging.level must be DEBUG, INFO, WARNING, ERROR or CRITICAL"
        raise ConfigurationError(message)
    if not isinstance(console, bool) or (log_file is not None and (not isinstance(log_file, str) or not log_file)):
        message = "logging.console must be boolean; logging.file must be a non-empty path"
        raise ConfigurationError(message)
    log_path = (source_path.parent / Path(log_file).expanduser()).resolve() if log_file else None
    return FrameworkConfig(devices, LoggingConfig(level.upper(), console, log_path), source_path)


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
