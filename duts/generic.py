"""Generic DUT composition, independent of model names and test frameworks."""

from typing import Any, Self

from embedded_framework.configurator.configurator_dut import (
    DeviceConfig,
    EngineFactory,
)
from embedded_framework.helpers.he_common import CommonHelpers
from embedded_framework.helpers.he_shell import CommandResult, ShellHelper
from embedded_framework.lib.custom_exception import EmbeddedFrameworkException


class DeviceStateError(EmbeddedFrameworkException):
    """The requested operation is unavailable in the current DUT state."""


class GenericDUT:
    """Own configured engines and release them in reverse initialization order."""

    def __init__(
        self,
        config: DeviceConfig,
        factory: EngineFactory,
    ) -> None:
        self.config = config
        self.name = config.name
        self.helpers = CommonHelpers()
        self._factory = factory
        self._engines: dict[str, Any] = {}
        self._connected = False

    @property
    def is_initialized(self) -> bool:
        """True when all configured engines were initialized successfully."""
        return self._connected

    def connect(self) -> Self:
        """Initialize connections transactionally; repeated successful calls are harmless."""
        if self._connected:
            return self

        if self._engines:
            message = "Previous cleanup failed; close the DUT before reconnecting"
            raise DeviceStateError(message)

        # Validate all connections before creating any engine.
        for connection in self.config.connections.values():
            self._factory.validate(connection)

        try:
            for name, connection in self.config.connections.items():
                self._engines[name] = self._factory.create(connection)

            self._connected = True

        except BaseException as error:
            try:
                self.close()
            except Exception as cleanup_error:  # noqa: BLE001
                error.add_note(
                    f"DUT initialization cleanup also failed: "
                    f"{type(cleanup_error).__name__}"
                )
            raise

        return self

    def engine(self, name: str | None = None) -> Any:
        """Return a named engine, or the configured default connection."""
        if not self._connected:
            message = f"DUT {self.name} is not initialized"
            raise DeviceStateError(message)

        return self._engines[
            name or self.config.default_connection
        ]

    def execute(
        self,
        command: str,
        timeout: float = 30,
        *,
        connection: str | None = None,
        check: bool = True,
    ) -> CommandResult:
        """Execute through a command-capable engine.

        :param connection: Engine alias; defaults to the DUT's default connection.
        :param check: Raise CommandError on a non-zero exit status when True.
        :raises DeviceStateError: If the selected protocol has no command capability.
        """
        if timeout <= 0:
            message = "Command timeout must be positive"
            raise ValueError(message)

        execute = getattr(
            self.engine(connection),
            "do_command_w_exitstatus",
            None,
        )

        if not callable(execute):
            message = "The selected connection does not support shell commands"
            raise DeviceStateError(message)

        stdout, status, stderr = execute(
            command,
            time_out=timeout,
        )

        result = CommandResult(
            stdout,
            status,
            stderr,
        )

        return result.check() if check else result

    def shell(
        self,
        connection: str | None = None,
    ) -> ShellHelper:
        return ShellHelper(
            self.engine(connection)
        )
    
    def close(self) -> None:
        """Attempt every close; retain failed engines for a caller's cleanup retry."""
        self._connected = False
        errors = []

        for name, engine in reversed(list(self._engines.items())):
            try:
                engine.close()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
            else:
                del self._engines[name]

        if errors:
            message = f"Failed to close connections for DUT {self.name}"
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
                f"DUT cleanup also failed: "
                f"{type(cleanup_error).__name__}"
            )


def make_dut(
    config: DeviceConfig,
    *,
    factory: EngineFactory | None = None,
) -> GenericDUT:
    """Create a configured DUT without contacting it; use connect() or a context manager."""
    return GenericDUT(
        config,
        factory or EngineFactory(),
    )