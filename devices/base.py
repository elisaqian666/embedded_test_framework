"""Device adapters and their common connection lifecycle."""

from enum import StrEnum
from threading import RLock
from typing import Any, Self

from embedded_test_framework.configurator.configurator_dut import DeviceConfig, EngineFactory
from embedded_test_framework.lib.custom_exception import EmbeddedFrameworkException


class DeviceStateError(EmbeddedFrameworkException):
    """The requested operation is unavailable in the current device state."""


class Capability(StrEnum):
    CAN = "can"
    MQTT = "mqtt"
    MODBUS = "modbus"
    REGISTER_IO = "register_io"
    DIGITAL_IO = "digital_io"
    SERIAL = "serial"
    SHELL = "shell"
    ADB = "adb"


class BaseDevice:
    """Own configured transports and expose common device operations."""

    capabilities: frozenset[Capability] = frozenset()
    connection_capabilities: dict[Capability, frozenset[str]] = {}

    def __init__(self, config: DeviceConfig, factory: EngineFactory) -> None:
        self.config = config
        self.name = config.name
        self._factory = factory
        self._engines: dict[str, Any] = {}
        self._connected = False
        self._lock = RLock()

    def supports(self, capability: Capability) -> bool:
        """Report configured capabilities without probing live device health."""
        return capability in self.capabilities or any(
            connection.protocol in self.connection_capabilities.get(capability, ()) for connection in self.config.connections.values()
        )

    def require(self, capability: Capability) -> None:
        if not self.supports(capability):
            raise DeviceStateError(f"DUT {self.name} does not support {capability}")

    @property
    def is_initialized(self) -> bool:
        """Whether the connection set is prepared, not whether the DUT is alive."""
        return self._connected

    def connect(self) -> Self:
        with self._lock:
            if self._connected:
                return self
            if self._engines:
                raise DeviceStateError("Previous cleanup failed; close the DUT before reconnecting")
            try:
                for name, connection in self.config.connections.items():
                    if connection.required:
                        self._engines[name] = self._factory.create(connection)
                self._connected = True
            except BaseException as error:
                try:
                    self.close()
                except Exception as cleanup_error:  # noqa: BLE001
                    error.add_note(f"DUT initialization cleanup also failed: {type(cleanup_error).__name__}")
                raise
            return self

    def engine(self, name: str | None = None, *, protocol: str | None = None) -> Any:
        """Select an explicit alias, matching default, or unique protocol connection."""
        with self._lock:
            if not self._connected:
                raise DeviceStateError(f"DUT {self.name} is not initialized")
            if name is not None and (not isinstance(name, str) or not name):
                raise DeviceStateError("Connection alias must be a non-empty string")
            if name is None:
                name = self.config.default_connection
                if protocol is not None and (name not in self.config.connections or self.config.connections[name].protocol != protocol):
                    matches = [alias for alias, config in self.config.connections.items() if config.protocol == protocol]
                    if len(matches) != 1:
                        raise DeviceStateError(
                            f"DUT {self.name} requires an explicit connection: found {len(matches)} connections for {protocol}"
                        )
                    name = matches[0]
            if name not in self.config.connections:
                raise DeviceStateError(f"Unknown connection {name!r} for DUT {self.name}")
            connection = self.config.connections[name]
            if protocol is not None and connection.protocol != protocol:
                raise DeviceStateError(f"Connection {name!r} uses {connection.protocol}, expected {protocol}")
            if name not in self._engines:
                self._engines[name] = self._factory.create(connection)
            return self._engines[name]

    def close(self) -> None:
        with self._lock:
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
        from embedded_test_framework.devices.android.android_device import AndroidDevice
        from embedded_test_framework.devices.linux.linux_device import LinuxDevice
        from embedded_test_framework.devices.mcu.stm32 import Stm32Device
        from embedded_test_framework.devices.plc.modbus_plc import ModbusPLCDevice

        self._adapters = {
            "android": AndroidDevice,
            "generic": BaseDevice,
            "linux": LinuxDevice,
            "modbus_plc": ModbusPLCDevice,
            "stm32": Stm32Device,
        }
        self._adapters.update(adapters or {})

    def create(self, config: DeviceConfig, factory: EngineFactory) -> BaseDevice:
        kind = config.metadata.get("type", "generic")
        if not isinstance(kind, str) or kind not in self._adapters:
            raise ValueError(f"Unsupported device type: {kind}")
        return self._adapters[kind](config, factory)
