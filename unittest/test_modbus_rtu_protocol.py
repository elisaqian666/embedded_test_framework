import pytest

from embedded_framework.communication.base import BaseTransport
from embedded_framework.configurator.configurator_dut import DeviceConfig, EngineFactory
from embedded_framework.devices.plc import ModbusPLCDevice
from embedded_framework.protocols.modbus.rtu import ModbusRTUProtocol


class FakeTransport(BaseTransport):
    def __init__(self, response: bytes = b"") -> None:
        self.response = bytearray(response)
        self.requests: list[bytes] = []
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    @property
    def is_connected(self) -> bool:
        return self.connected

    def read(self, size: int) -> bytes:
        chunk, self.response = self.response[:size], self.response[size:]
        return bytes(chunk)

    def write(self, data: bytes) -> int:
        self.requests.append(data)
        return len(data)


def _frame(*body: int) -> bytes:
    data = bytes(body)
    return data + ModbusRTUProtocol._crc(data)


def test_read_holding_registers_builds_rtu_request_and_parses_response() -> None:
    transport = FakeTransport(_frame(1, 3, 4, 0, 1, 0, 2))

    assert ModbusRTUProtocol(transport, 1).read_holding_registers(0x10, 2) == [1, 2]
    assert transport.connected
    assert transport.requests == [_frame(1, 3, 0, 0x10, 0, 2)]


def test_write_register_builds_rtu_request() -> None:
    transport = FakeTransport(_frame(1, 6, 0, 0x64, 0, 0x7B))

    ModbusRTUProtocol(transport, 1).write_single_register(100, 123)

    assert transport.requests == [_frame(1, 6, 0, 0x64, 0, 0x7B)]


def test_plc_device_uses_the_injected_protocol_chain() -> None:
    transport = FakeTransport(_frame(1, 3, 2, 0, 7))
    protocol = ModbusRTUProtocol(transport, 1)
    device = ModbusPLCDevice(DeviceConfig("plc", {}, "", {}), EngineFactory(), protocol=protocol)

    assert device.read_register(0) == [7]
    assert transport.requests == [_frame(1, 3, 0, 0, 0, 1)]


def test_read_rejects_invalid_or_incomplete_responses() -> None:
    for response, error in (
        (b"\x01\x03\x02\x00\x01\x00\x00", ValueError),
        (_frame(2, 3, 2, 0, 1), ValueError),
        (_frame(1, 4, 2, 0, 1), ValueError),
        (b"\x01\x03", TimeoutError),
    ):
        with pytest.raises(error):
            ModbusRTUProtocol(FakeTransport(response), 1).read_holding_registers(0)
