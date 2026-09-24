"""DEPRECATED compatibility wrapper; use protocols.modbus.rtu instead."""

import logging

import serial
from serial.rs485 import RS485Settings

from embedded_framework.communication.base import BaseTransport
from embedded_framework.protocols.modbus.rtu import ModbusRTUProtocol


class _SerialSessionTransport(BaseTransport):
    """Adapt the old public ``serial.Serial`` argument to the transport contract."""

    def __init__(self, session: serial.Serial) -> None:
        self.session = session

    def connect(self) -> None:
        if not self.is_connected:
            self.session.open()

    def disconnect(self) -> None:
        self.session.close()

    @property
    def is_connected(self) -> bool:
        return bool(getattr(self.session, "is_open", False))

    def read(self, size: int) -> bytes:
        return self.session.read(size)

    def write(self, data: bytes) -> int:
        return self.session.write(data)


class ModbusRtuEngine:
    """Compatibility wrapper for the former serial-session Modbus RTU API."""

    def __init__(self, session: serial.Serial) -> None:
        self.serial_object = session
        self._transport = _SerialSessionTransport(session)
        self.logger = logging.getLogger("serial")

    _crc = staticmethod(ModbusRTUProtocol._crc)

    def _protocol(self, slave: int) -> ModbusRTUProtocol:
        return ModbusRTUProtocol(self._transport, slave)

    def read_holding_registers(self, slave: int, address: int, count: int = 1) -> list[int]:
        """Read 1..125 16-bit holding registers (function 0x03)."""
        return self._protocol(slave).read_holding_registers(address, count)

    def write_single_register(self, slave: int, address: int, value: int) -> None:
        """Write one unsigned 16-bit register (function 0x06)."""
        self._protocol(slave).write_single_register(address, value)

    def close(self) -> None:
        self._transport.disconnect()

    def __enter__(self):
        self._transport.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def make_modbus_rtu_engine(com_port, baudrate=9600, read_timeout=1.0, write_timeout=10, rs485=False):
    """Create a Modbus RTU engine; set rs485 for adapters requiring RTS direction control."""
    session = serial.Serial(timeout=read_timeout, write_timeout=write_timeout)
    session.port, session.baudrate = com_port, baudrate
    if rs485:
        session.rs485_mode = RS485Settings()
    return ModbusRtuEngine(session)
