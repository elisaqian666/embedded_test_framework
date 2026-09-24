import pytest

pytest.importorskip("serial")

from embedded_framework.communication.base import BaseTransport
from embedded_framework.communication.serial import SerialTransport
from embedded_framework.communication.socket import SocketTransport


def test_transports_share_the_lifecycle_contract() -> None:
    assert issubclass(SerialTransport, BaseTransport)
    assert issubclass(SocketTransport, BaseTransport)
