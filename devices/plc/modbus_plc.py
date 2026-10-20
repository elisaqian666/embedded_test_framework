from embedded_test_framework.devices.base import BaseDevice, Capability


class ModbusPLCDevice(BaseDevice):
    """PLC adapter for the framework's Modbus register operations."""

    connection_capabilities = {Capability.MODBUS: frozenset({"modbus"}), Capability.REGISTER_IO: frozenset({"modbus"})}

    def read_holding_registers(self, slave: int, address: int, count: int = 1, *, connection: str | None = None) -> list[int]:
        return self.engine(connection, protocol="modbus").read_holding_registers(slave, address, count)

    def write_single_register(self, slave: int, address: int, value: int, *, connection: str | None = None) -> None:
        self.engine(connection, protocol="modbus").write_single_register(slave, address, value)
