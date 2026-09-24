"""Device-neutral Modbus operations used by PLC adapters."""

from abc import ABC, abstractmethod


class BaseModbusProtocol(ABC):
    @abstractmethod
    def read_holding_registers(self, address: int, count: int = 1) -> list[int]:
        """Read holding registers for the configured slave."""

    @abstractmethod
    def write_single_register(self, address: int, value: int) -> None:
        """Write one holding register for the configured slave."""
