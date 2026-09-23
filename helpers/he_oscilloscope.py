"""LAN/SCPI control for a RIGOL DS1102Z-E oscilloscope."""

import argparse
import platform
import socket
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class IOscilloscope(ABC):
    """Common control contract for LAN-connected oscilloscopes."""

    @abstractmethod
    def ping(self) -> bool:
        ...

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def command(self, scpi: str) -> None:
        ...

    @abstractmethod
    def query(self, scpi: str) -> str:
        ...

    @abstractmethod
    def identify(self) -> str:
        ...

    @abstractmethod
    def run(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def single(self) -> None:
        ...

    @abstractmethod
    def autoscale(self) -> None:
        ...

    @abstractmethod
    def save_screenshot(self, destination: str | Path) -> Path:
        ...


class RigolOscilloscope(IOscilloscope):
    """Control a RIGOL DS1102Z-E through its SCPI TCP service."""

    MODEL = "DS1102Z-E"

    def __init__(self, host: str, port: int = 5555, timeout: float = 5) -> None:
        if not host or not 1 <= port <= 65535 or timeout <= 0:
            raise ValueError("host, port (1..65535), and timeout must be valid")
        self.host, self.port, self.timeout = host, port, timeout
        self._socket: socket.socket | None = None

    def ping(self) -> bool:
        """Return whether the oscilloscope responds to one ICMP echo request."""
        flag = "-n" if platform.system() == "Windows" else "-c"
        return subprocess.run(["ping", flag, "1", self.host], capture_output=True, timeout=self.timeout).returncode == 0

    def connect(self, *, check_ping: bool = True) -> None:
        """Ping, connect, and verify that the instrument is a DS1102Z-E."""
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

    def close(self) -> None:
        """Close the persistent SCPI connection."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def command(self, scpi: str) -> None:
        """Send one SCPI command."""
        if not scpi.strip():
            raise ValueError("SCPI command must not be empty")
        self.connect()
        self._socket.sendall((scpi.rstrip("\r\n") + "\n").encode())

    def query(self, scpi: str) -> str:
        """Send one SCPI query and return its response."""
        if not scpi.strip().endswith("?"):
            raise ValueError("SCPI query must end with '?'")
        self.connect()
        return self._query_connected(scpi)

    def _query_connected(self, scpi: str) -> str:
        self._socket.sendall((scpi.rstrip("\r\n") + "\n").encode())
        return self._read_until(b"\n").decode().strip()

    def _read_until(self, delimiter: bytes) -> bytes:
        data = bytearray()
        while not data.endswith(delimiter):
            if not (chunk := self._socket.recv(4096)):
                raise ConnectionError("Oscilloscope closed the connection")
            data.extend(chunk)
        return bytes(data)

    def _read_exactly(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            if not (chunk := self._socket.recv(size - len(data))):
                raise ConnectionError("Oscilloscope closed the connection")
            data.extend(chunk)
        return bytes(data)

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
        """Save the current display as a PNG image and return its path."""
        self.connect()
        self._socket.sendall(b":DISP:DATA? ON,OFF,PNG\n")
        if self._read_exactly(1) != b"#":
            raise ValueError("Invalid screenshot response header")
        width = int(self._read_exactly(1))
        length = int(self._read_exactly(width))
        image = self._read_exactly(length)
        self._read_exactly(1)  # DS1102Z-E terminates image data with LF.
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image)
        return target

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Control a RIGOL DS1102Z-E over LAN SCPI")
    parser.add_argument("host", help="oscilloscope IP address or hostname")
    parser.add_argument("action", choices=("idn", "run", "stop", "single", "autoscale", "screenshot", "command", "query"))
    parser.add_argument("scpi", nargs="?", help="SCPI text for command/query actions, or screenshot path")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    if args.action in {"command", "query", "screenshot"} and not args.scpi:
        parser.error("scpi or screenshot path is required")
    with RigolOscilloscope(args.host, args.port, args.timeout) as scope:
        method = getattr(scope, {"idn": "identify", "screenshot": "save_screenshot"}.get(args.action, args.action))
        result = method(args.scpi) if args.scpi else method()
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
