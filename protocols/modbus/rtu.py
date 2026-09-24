"""Modbus RTU framing over an injected byte transport."""

from embedded_framework.communication.base import BaseTransport
from embedded_framework.protocols.modbus.base import BaseModbusProtocol


class ModbusRTUProtocol(BaseModbusProtocol):
    def __init__(self, transport: BaseTransport, slave_id: int) -> None:
        if not 1 <= slave_id <= 247:
            raise ValueError("slave_id must be 1..247")
        if not callable(getattr(transport, "read", None)) or not callable(getattr(transport, "write", None)):
            raise TypeError("Modbus RTU requires a byte-readable transport")
        self.transport, self.slave_id = transport, slave_id

    @staticmethod
    def _crc(frame: bytes) -> bytes:
        value = 0xFFFF
        for byte in frame:
            value ^= byte
            for _ in range(8):
                value = (value >> 1) ^ (0xA001 if value & 1 else 0)
        return value.to_bytes(2, "little")

    def _read_exactly(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            if not (chunk := self.transport.read(size - len(data))):
                raise TimeoutError("Timed out waiting for Modbus RTU response")
            data.extend(chunk)
        return bytes(data)

    def _send(self, function: int, payload: bytes) -> None:
        self.transport.connect()
        frame = bytes((self.slave_id, function)) + payload
        self.transport.write(frame + self._crc(frame))

    def _verify(self, response: bytes, function: int) -> None:
        if response[-2:] != self._crc(response[:-2]):
            raise ValueError("Invalid Modbus RTU CRC")
        if response[0] != self.slave_id:
            raise ValueError("Response came from a different Modbus slave")
        if response[1] == function | 0x80:
            raise RuntimeError(f"Modbus exception {response[2]}")
        if response[1] != function:
            raise ValueError("Unexpected Modbus function code")

    def read_holding_registers(self, address: int, count: int = 1) -> list[int]:
        if not 0 <= address <= 65535 or not 1 <= count <= 125:
            raise ValueError("address must be 0..65535 and count must be 1..125")
        self._send(3, address.to_bytes(2, "big") + count.to_bytes(2, "big"))
        header = self._read_exactly(3)
        if header[1] == 0x83:
            response = header + self._read_exactly(2)
            self._verify(response, 3)
        if header[2] != count * 2:
            raise ValueError("Unexpected Modbus register count")
        response = header + self._read_exactly(header[2] + 2)
        self._verify(response, 3)
        return [int.from_bytes(response[index : index + 2], "big") for index in range(3, 3 + header[2], 2)]

    def write_single_register(self, address: int, value: int) -> None:
        if not all(type(item) is int and 0 <= item <= 65535 for item in (address, value)):
            raise ValueError("address and value must be 0..65535")
        payload = address.to_bytes(2, "big") + value.to_bytes(2, "big")
        self._send(6, payload)
        response = self._read_exactly(8)
        self._verify(response, 6)
        if response[2:6] != payload:
            raise ValueError("Modbus write response does not match request")
