import pytest

from embedded_test_framework.protocols.scpi import ScpiProtocol


class FakeSocket:
    def __init__(self, response: bytes = b"") -> None:
        self.response = bytearray(response)
        self.sent: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        chunk, self.response = self.response[:size], self.response[size:]
        return bytes(chunk)


def test_scpi_query_frames_command_and_preserves_buffered_response() -> None:
    socket = FakeSocket(b"RIGOL\nNEXT\n")
    scpi = ScpiProtocol(socket)

    assert scpi.query("*IDN?") == "RIGOL"
    assert scpi.read_until(b"\n") == b"NEXT\n"
    assert socket.sent == [b"*IDN?\n"]


def test_scpi_rejects_invalid_commands() -> None:
    scpi = ScpiProtocol(FakeSocket())

    with pytest.raises(ValueError):
        scpi.command(" ")
    with pytest.raises(ValueError):
        scpi.query("*IDN")
