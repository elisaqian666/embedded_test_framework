"""Single initialization entry point for the generic embedded-device framework."""

from pathlib import Path
from typing import Any, Self

from embedded_framework.configurator.configurator_dut import EngineFactory, FrameworkConfig, load_config, load_mapping
from embedded_framework.duts.generic import GenericDUT, make_dut
from embedded_framework.helpers.he_common import CommonHelpers
from embedded_framework.lib import assertion
from embedded_framework.lib.logger import LoggingSession


def _secrets(value: Any, *, sensitive: bool = False) -> list[str]:
    if isinstance(value, dict):
        return [
            secret
            for key, item in value.items()
            for secret in _secrets(
                item,
                sensitive=sensitive
                or any(word in key.lower() for word in ("password", "secret", "token", "auth", "key", "cookie", "credential")),
            )
        ]
    if isinstance(value, (list, tuple)):
        return [secret for item in value for secret in _secrets(item, sensitive=sensitive)]
    return [value] if sensitive and isinstance(value, str) and value else []


class Runtime:
    """Own one configuration, logging scope, helper set and collection of DUTs."""

    def __init__(self, config: FrameworkConfig, *, factory: EngineFactory | None = None) -> None:
        self.config = config
        self._factory = factory or EngineFactory()
        # Validate every device before opening the first connection or log file.
        for device in config.devices.values():
            for connection in device.connections.values():
                self._factory.validate(connection)
        secrets = [
            secret
            for device in config.devices.values()
            for connection in device.connections.values()
            for secret in _secrets(connection.options)
        ]
        self._logging = LoggingSession(config.logging, secrets=secrets)
        self.logger = self._logging.logger
        self.helpers = CommonHelpers()
        self.assertions = assertion
        self.duts: dict[str, GenericDUT] = {
            name: make_dut(device, factory=self._factory, logger=self.logger.getChild(name)) for name, device in config.devices.items()
        }
        self._closed = False

    def connect(self) -> Self:
        """Initialize every DUT; release all owned resources on partial failure."""
        if self._closed:
            message = "Runtime is closed; initialize a new runtime"
            raise RuntimeError(message)
        try:
            for dut in self.duts.values():
                dut.connect()
        except BaseException as error:
            try:
                self.close()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve the original initialization error
                error.add_note(f"Runtime cleanup also failed: {type(cleanup_error).__name__}")
            raise
        return self

    def close(self) -> None:
        """Release all DUT connections and logging handles, even when one close fails."""
        errors = []
        for dut in reversed(list(self.duts.values())):
            try:
                dut.close()
            except Exception as error:  # noqa: BLE001 - attempt every DUT cleanup
                errors.append(error)
        try:
            self._logging.close()
        except Exception as error:  # noqa: BLE001 - include logging cleanup errors alongside DUT errors
            errors.append(error)
        self._closed = True
        if errors:
            message = "Runtime cleanup failed"
            raise ExceptionGroup(message, errors)

    def __enter__(self) -> Self:
        return self.connect()

    def __exit__(self, _exc_type: object, error: BaseException | None, _traceback: object) -> None:
        try:
            self.close()
        except Exception as cleanup_error:
            if error is None:
                raise
            error.add_note(f"Runtime cleanup also failed: {type(cleanup_error).__name__}")


def initialize(
    path: str | Path, *, overrides: dict[str, Any] | None = None, factory: EngineFactory | None = None, connect: bool = True
) -> Runtime:
    """Load config, prepare logging/helpers/DUTs, and optionally open connections.

    :param path: JSON or TOML configuration file.
    :param overrides: Values recursively merged over the file configuration.
    :param factory: Optional custom protocol registry, scoped to this runtime.
    :param connect: False prepares and validates without contacting devices.
    :returns: Runtime; use as a context manager or explicitly call close().

    Example::

        with initialize("devices.toml") as runtime:
            result = runtime.duts["board"].execute("uname -a")
            runtime.assertions.assert_equal(result.exit_status, 0)
    """
    runtime = Runtime(load_config(path, overrides=overrides), factory=factory)
    return runtime.connect() if connect else runtime


def initialize_from_mapping(
    values: dict[str, Any], *, source: str | Path = "embedded_test_config.py", factory: EngineFactory | None = None, connect: bool = True
) -> Runtime:
    """Initialize generic DUTs from a validated configuration mapping."""
    runtime = Runtime(load_mapping(values, source=source), factory=factory)
    return runtime.connect() if connect else runtime
