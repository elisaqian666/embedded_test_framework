import pytest

pytest.importorskip("serial")

from embedded_test_framework.communication.base import BaseTransport
from embedded_test_framework.communication.serial import SerialTransport
from embedded_test_framework.communication.socket import SocketTransport


def test_transports_share_the_lifecycle_contract() -> None:
    assert issubclass(SerialTransport, BaseTransport)
    assert issubclass(SocketTransport, BaseTransport)


@pytest.mark.parametrize("already_open", [False, True])
def test_serial_open_and_line_read_preserve_first_line(already_open):
    from unittest.mock import Mock

    session = Mock()
    session.isOpen.side_effect = lambda: session.is_open
    session.is_open = already_open
    session.open.side_effect = lambda: setattr(session, "is_open", True)
    session.readline.side_effect = [b"boot ready\n", b"next line\n", b""]
    transport = SerialTransport(session, "COM1")
    transport.check_serial_connection_open()
    session.readline.assert_not_called()
    assert transport.read_line_on_serial() == "boot ready\n"
    session.readline.assert_called_once()
    assert transport.read_line_on_serial() == "next line\n"
    assert session.open.call_count == (0 if already_open else 1)


def test_serial_command_does_not_discard_device_response():
    from unittest.mock import Mock

    session = Mock()
    session.isOpen.return_value = False
    session.readline.side_effect = [b"OK\n", b"unsolicited log\n", b""]
    session.write.return_value = 3
    transport = SerialTransport(session, "COM1")
    assert transport.send_cmd_and_read_line_on_serial("AT") == "OK\n"
    session.write.assert_called_once_with(b"AT\n")
    session.readline.assert_called_once()
