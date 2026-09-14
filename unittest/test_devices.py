from unittest.mock import Mock
import pytest
from embedded_test_framework import Device, ConfigurationError
from embedded_test_framework.engine import FTPTransport, SerialTransport, MemoryTransport


def test_device_routes_byte_and_file_capabilities():
    serial = SerialTransport("unused")
    ftp = FTPTransport("unused")
    for engine in (serial, ftp):
        engine.connect = Mock()
        engine.close = Mock()
    serial.exchange = Mock(return_value=b"OK\n")
    ftp.upload = Mock()
    ftp.download = Mock(return_value="local.bin")
    with Device("dut", {"console": serial, "files": ftp}) as device:
        assert device.exchange(b"AT\n") == b"OK\n"
        serial.exchange.assert_called_once_with(b"AT\n")
        device.upload("local.bin", "remote.bin")
        ftp.upload.assert_called_once_with("local.bin", "remote.bin")
        assert device.download("remote.bin", "local.bin") == "local.bin"
    serial.close.assert_called_once()
    ftp.close.assert_called_once()


def test_shared_channel_rejected():
    engine = MemoryTransport()
    with pytest.raises(ConfigurationError):
        Device("dut", {"a": engine, "b": engine})
