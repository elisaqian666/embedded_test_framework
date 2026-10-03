"""SCPI text framing and response buffering."""

from typing import Any


class ScpiProtocol:
    """Send SCPI commands through a socket-like byte transport."""

    def __init__(self, transport: Any) -> None:
        if not callable(getattr(transport, "sendall", None)) or not callable(getattr(transport, "recv", None)):
            raise TypeError("SCPI requires a socket-like byte transport")
        self.transport = transport
        self._buffer = bytearray()

    @staticmethod
    def _command(scpi: str) -> bytes:
        if not scpi.strip():
            raise ValueError("SCPI command must not be empty")
        return (scpi.rstrip("\r\n") + "\n").encode()

    def command(self, scpi: str) -> None:
        self.transport.sendall(self._command(scpi))

    def query(self, scpi: str) -> str:
        if not scpi.strip().endswith("?"):
            raise ValueError("SCPI query must end with '?'")
        self.command(scpi)
        return self.read_until(b"\n").decode().strip()

    def read_until(self, delimiter: bytes) -> bytes:
        while (end := self._buffer.find(delimiter)) < 0:
            if not (chunk := self.transport.recv(4096)):
                raise ConnectionError("SCPI transport closed the connection")
            self._buffer.extend(chunk)
        end += len(delimiter)
        data = bytes(self._buffer[:end])
        del self._buffer[:end]
        return data

    def read_exactly(self, size: int) -> bytes:
        while len(self._buffer) < size:
            if not (chunk := self.transport.recv(4096)):
                raise ConnectionError("SCPI transport closed the connection")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data
