"""LAN/SCPI control for a RIGOL DS1102Z-E oscilloscope."""

import platform
import socket
import subprocess
from pathlib import Path


class Oscilloscope:
    """Control a RIGOL DS1102Z-E through its SCPI TCP service."""

    MODEL = "DS1102Z-E"

    def __init__(self, host: str, port: int = 5555, timeout: float = 5) -> None:
        if not host or not 1 <= port <= 65535 or timeout <= 0:
            raise ValueError("host, port (1..65535), and timeout must be valid")
        self.host, self.port, self.timeout = host, port, timeout
        self._socket: socket.socket | None = None
        self._buffer = bytearray()

    def ping(self) -> bool:
        flag = "-n" if platform.system() == "Windows" else "-c"
        return subprocess.run(["ping", flag, "1", self.host], capture_output=True, timeout=self.timeout).returncode == 0

    def connect(self, *, check_ping: bool = True) -> None:
        """Connect and verify the expected RIGOL model with ``*IDN?``."""
        if self._socket is not None:
            return
        if check_ping and not self.ping():
            raise ConnectionError(f"Oscilloscope does not respond to ping: {self.host}")
        self._socket = socket.create_connection((self.host, self.port), self.timeout)
        try:
            if self.MODEL not in self._query_connected("*IDN?").upper():
                raise ConnectionError(f"Expected RIGOL {self.MODEL}")
        except BaseException:
            self.close()
            raise

    def disconnect(self) -> None:
        self.close()

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._buffer.clear()

    def command(self, scpi: str) -> None:
        if not scpi.strip():
            raise ValueError("SCPI command must not be empty")
        self.connect()
        self._socket.sendall((scpi.rstrip("\r\n") + "\n").encode())

    def query(self, scpi: str) -> str:
        if not scpi.strip().endswith("?"):
            raise ValueError("SCPI query must end with '?'")
        self.connect()
        return self._query_connected(scpi)

    def _query_connected(self, scpi: str) -> str:
        self._socket.sendall((scpi.rstrip("\r\n") + "\n").encode())
        return self._read_until(b"\n").decode().strip()

    def _read_until(self, delimiter: bytes) -> bytes:
        while (end := self._buffer.find(delimiter)) < 0:
            if not (chunk := self._socket.recv(4096)):
                raise ConnectionError("Oscilloscope closed the connection")
            self._buffer.extend(chunk)
        end += len(delimiter)
        data = bytes(self._buffer[:end])
        del self._buffer[:end]
        return data

    def _read_exactly(self, size: int) -> bytes:
        while len(self._buffer) < size:
            if not (chunk := self._socket.recv(4096)):
                raise ConnectionError("Oscilloscope closed the connection")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def identify(self) -> str:
        return self.query("*IDN?")

    def run(self) -> None:
        self.command(":RUN")

    def stop(self) -> None:
        self.command(":STOP")

    def single(self) -> None:
        self.command(":SING")

    def autoscale(self) -> None:
        self.command(":AUT")

    def save_screenshot(self, destination: str | Path) -> Path:
        self.connect()
        self._socket.sendall(b":DISP:DATA? ON,OFF,PNG\n")
        if self._read_exactly(1) != b"#":
            raise ValueError("Invalid screenshot response header")
        width = int(self._read_exactly(1))
        length = int(self._read_exactly(width))
        image = self._read_exactly(length)
        self._read_exactly(1)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image)
        return target

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
