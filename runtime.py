"""Single initialization entry point for the generic embedded-device framework."""

from pathlib import Path
from typing import Any, Self

from embedded_framework.configurator.configurator_dut import (
    EngineFactory,
    FrameworkConfig,
    load_config,
    load_mapping,
)
from embedded_framework.duts.generic import GenericDUT, make_dut
from embedded_framework.helpers.he_common import CommonHelpers
from embedded_framework.lib import assertion


class Runtime:
    """Own one configuration, helper set and collection of DUTs."""

    def __init__(
        self,
        config: FrameworkConfig,
        *,
        factory: EngineFactory | None = None,
    ) -> None:
        self.config = config
        self._factory = factory or EngineFactory()

        # Validate every device before opening the first connection.
        for device in config.devices.values():
            for connection in device.connections.values():
                self._factory.validate(connection)

        self.helpers = CommonHelpers()
        self.assertions = assertion

        self.duts: dict[str, GenericDUT] = {
            name: make_dut(
                device,
                factory=self._factory,
            )
            for name, device in config.devices.items()
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
            except Exception as cleanup_error:  # noqa: BLE001
                error.add_note(
                    f"Runtime cleanup also failed: "
                    f"{type(cleanup_error).__name__}"
                )
            raise

        return self

    def close(self) -> None:
        """Release all DUT connections, even when one close fails."""
        errors = []

        for dut in reversed(list(self.duts.values())):
            try:
                dut.close()
            except Exception as error:  # noqa: BLE001
                errors.append(error)

        self._closed = True

        if errors:
            message = "Runtime cleanup failed"
            raise ExceptionGroup(message, errors)

    def __enter__(self) -> Self:
        return self.connect()

    def __exit__(
        self,
        _exc_type: object,
        error: BaseException | None,
        _traceback: object,
    ) -> None:
        try:
            self.close()
        except Exception as cleanup_error:
            if error is None:
                raise

            error.add_note(
                f"Runtime cleanup also failed: "
                f"{type(cleanup_error).__name__}"
            )


def initialize(
    path: str | Path,
    *,
    overrides: dict[str, Any] | None = None,
    factory: EngineFactory | None = None,
    connect: bool = True,
) -> Runtime:
    """Load config, prepare helpers/DUTs, and optionally open connections.

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
    runtime = Runtime(
        load_config(path, overrides=overrides),
        factory=factory,
    )

    return runtime.connect() if connect else runtime


def initialize_from_mapping(
    values: dict[str, Any],
    *,
    source: str | Path = "embedded_test_config.py",
    factory: EngineFactory | None = None,
    connect: bool = True,
) -> Runtime:
    """Initialize generic DUTs from a validated configuration mapping."""
    runtime = Runtime(
        load_mapping(values, source=source),
        factory=factory,
    )

    return runtime.connect() if connect else runtime