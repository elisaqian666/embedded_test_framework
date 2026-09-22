"""Minimal Modbus RTU transport for RS-485 serial adapters."""

import logging

import serial
from serial.rs485 import RS485Settings


class ModbusRtuEngine:
    """Read holding registers and write single registers over Modbus RTU."""

    def __init__(self, session: serial.Serial) -> None:
        self.serial_object = session
        self.logger = logging.getLogger("serial")

    @staticmethod
    def _crc(frame: bytes) -> bytes:
        value = 0xFFFF
        for byte in frame:
            value ^= byte
            for _ in range(8):
                value = (value >> 1) ^ (0xA001 if value & 1 else 0)
        return value.to_bytes(2, "little")

    def _open(self) -> None:
        if not self.serial_object.is_open:
            self.serial_object.open()

    def _read_exactly(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            if not (chunk := self.serial_object.read(size - len(result))):
                raise TimeoutError("Timed out waiting for Modbus RTU response")
            result.extend(chunk)
        return bytes(result)

    def _send(self, slave: int, function: int, payload: bytes) -> None:
        if type(slave) is not int or not 1 <= slave <= 247:
            raise ValueError("slave must be 1..247")
        self._open()
        self.serial_object.reset_input_buffer()
        frame = bytes((slave, function)) + payload
        self.serial_object.write(frame + self._crc(frame))

    @classmethod
    def _verify(cls, response: bytes, slave: int, function: int) -> None:
        if response[-2:] != cls._crc(response[:-2]):
            raise ValueError("Invalid Modbus RTU CRC")
        if response[0] != slave:
            raise ValueError("Response came from a different Modbus slave")
        if response[1] == function | 0x80:
            raise RuntimeError(f"Modbus exception {response[2]}")
        if response[1] != function:
            raise ValueError("Unexpected Modbus function code")

    def read_holding_registers(self, slave: int, address: int, count: int = 1) -> list[int]:
        """Read 1..125 16-bit holding registers (function 0x03)."""
        if not 0 <= address <= 65535 or not 1 <= count <= 125:
            raise ValueError("address must be 0..65535 and count must be 1..125")
        self._send(slave, 3, address.to_bytes(2, "big") + count.to_bytes(2, "big"))
        header = self._read_exactly(3)
        if header[1] == 0x83:
            response = header + self._read_exactly(2)
            self._verify(response, slave, 3)
        if header[2] != count * 2:
            raise ValueError("Unexpected Modbus register count")
        response = header + self._read_exactly(header[2] + 2)
        self._verify(response, slave, 3)
        return [int.from_bytes(response[index : index + 2], "big") for index in range(3, 3 + header[2], 2)]

    def write_single_register(self, slave: int, address: int, value: int) -> None:
        """Write one unsigned 16-bit register (function 0x06)."""
        if not all(type(item) is int and 0 <= item <= 65535 for item in (address, value)):
            raise ValueError("address and value must be 0..65535")
        payload = address.to_bytes(2, "big") + value.to_bytes(2, "big")
        self._send(slave, 6, payload)
        response = self._read_exactly(8)
        self._verify(response, slave, 6)
        if response[2:6] != payload:
            raise ValueError("Modbus write response does not match request")

    def close(self) -> None:
        self.serial_object.close()

    def __enter__(self):
        self._open()
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
