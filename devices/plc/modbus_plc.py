from embedded_test_framework.devices.base import BaseDevice, Capability


class ModbusPLCDevice(BaseDevice):
    """PLC adapter for the framework's Modbus register operations."""

    capabilities = frozenset({Capability.MODBUS, Capability.REGISTER_IO})

    def read_holding_registers(self, slave: int, address: int, count: int = 1, *, connection: str | None = None) -> list[int]:
        self.require(Capability.MODBUS)
        return self.engine(connection).read_holding_registers(slave, address, count)

    def write_single_register(self, slave: int, address: int, value: int, *, connection: str | None = None) -> None:
        self.require(Capability.MODBUS)
        self.engine(connection).write_single_register(slave, address, value)
