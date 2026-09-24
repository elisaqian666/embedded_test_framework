from embedded_framework.devices.base import BaseDevice, Capability, DeviceStateError
from embedded_framework.protocols.modbus.base import BaseModbusProtocol


class ModbusPLCDevice(BaseDevice):
    """PLC adapter for the framework's Modbus register operations."""

    capabilities = frozenset({Capability.MODBUS, Capability.REGISTER_IO})

    def __init__(self, config, factory, *, protocol: BaseModbusProtocol | None = None) -> None:
        super().__init__(config, factory)
        self.protocol = protocol

    def read_register(self, address: int, count: int = 1) -> list[int]:
        """Read holding registers through the configured Modbus protocol."""
        self.require(Capability.REGISTER_IO)
        if self.protocol is None:
            raise DeviceStateError("ModbusPLCDevice requires an injected Modbus protocol")
        return self.protocol.read_holding_registers(address, count)

    def write_register(self, address: int, value: int) -> None:
        """Write one holding register through the configured Modbus protocol."""
        self.require(Capability.REGISTER_IO)
        if self.protocol is None:
            raise DeviceStateError("ModbusPLCDevice requires an injected Modbus protocol")
        self.protocol.write_single_register(address, value)

    def read_holding_registers(self, slave: int, address: int, count: int = 1, *, connection: str | None = None) -> list[int]:
        self.require(Capability.MODBUS)
        return self.engine(connection).read_holding_registers(slave, address, count)

    def write_single_register(self, slave: int, address: int, value: int, *, connection: str | None = None) -> None:
        self.require(Capability.MODBUS)
        self.engine(connection).write_single_register(slave, address, value)
