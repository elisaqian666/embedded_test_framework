"""Device adapters and their common connection lifecycle."""

from enum import StrEnum
from typing import Any, Self

from embedded_framework.configurator.configurator_dut import DeviceConfig, EngineFactory
from embedded_framework.helpers.he_common import CommonHelpers
from embedded_framework.lib.custom_exception import EmbeddedFrameworkException


class DeviceStateError(EmbeddedFrameworkException):
    """The requested operation is unavailable in the current device state."""


class Capability(StrEnum):
    MODBUS = "modbus"
    REGISTER_IO = "register_io"
    DIGITAL_IO = "digital_io"
    SERIAL = "serial"
    SHELL = "shell"


class BaseDevice:
    """Own configured transports and expose common device operations."""

    capabilities: frozenset[Capability] = frozenset()

    def __init__(self, config: DeviceConfig, factory: EngineFactory) -> None:
        self.config = config
        self.name = config.name
        self.helpers = CommonHelpers()
        self._factory = factory
        self._engines: dict[str, Any] = {}
        self._connected = False

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def require(self, capability: Capability) -> None:
        if not self.supports(capability):
            raise DeviceStateError(f"DUT {self.name} does not support {capability}")

    @property
    def is_initialized(self) -> bool:
        return self._connected

    def connect(self) -> Self:
        if self._connected:
            return self
        if self._engines:
            raise DeviceStateError("Previous cleanup failed; close the DUT before reconnecting")
        try:
            for name, connection in self.config.connections.items():
                self._engines[name] = self._factory.create(connection)
            self._connected = True
        except BaseException as error:
            try:
                self.close()
            except Exception as cleanup_error:  # noqa: BLE001
                error.add_note(f"DUT initialization cleanup also failed: {type(cleanup_error).__name__}")
            raise
        return self

    def engine(self, name: str | None = None) -> Any:
        if not self._connected:
            raise DeviceStateError(f"DUT {self.name} is not initialized")
        return self._engines[name or self.config.default_connection]

    def close(self) -> None:
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
            raise ExceptionGroup(f"Failed to close connections for DUT {self.name}", errors)

    def __enter__(self) -> Self:
        return self.connect()

    def __exit__(self, _exc_type: object, error: BaseException | None, _traceback: object) -> None:
        try:
            self.close()
        except Exception as cleanup_error:
            if error is None:
                raise
            error.add_note(f"DUT cleanup also failed: {type(cleanup_error).__name__}")


class DeviceFactory:
    """Select a device adapter from ``devices.<name>.metadata.type``."""

    def __init__(self, adapters: dict[str, type[BaseDevice]] | None = None) -> None:
        from embedded_framework.devices.linux.linux_device import LinuxDevice
        from embedded_framework.devices.mcu.stm32 import Stm32Device
        from embedded_framework.devices.plc.modbus_plc import ModbusPLCDevice

        self._adapters = {"generic": BaseDevice, "linux": LinuxDevice, "modbus_plc": ModbusPLCDevice, "stm32": Stm32Device}
        self._adapters.update(adapters or {})

    def create(self, config: DeviceConfig, factory: EngineFactory) -> BaseDevice:
        kind = config.metadata.get("type", "generic")
        if not isinstance(kind, str) or kind not in self._adapters:
            raise ValueError(f"Unsupported device type: {kind}")
        return self._adapters[kind](config, factory)
