"""LAN/SCPI control for a RIGOL oscilloscope."""

import socket
from pathlib import Path

from embedded_test_framework.helpers.he_network import NetworkHelper
from embedded_test_framework.protocols.scpi import ScpiProtocol


class Oscilloscope:
    """Control a RIGOL oscilloscope through its SCPI TCP service."""

    MODEL = "DS1102Z-E"

    def __init__(self, host: str, port: int = 5555, timeout: float = 5, model: str = MODEL) -> None:
        if not host or not 1 <= port <= 65535 or timeout <= 0 or not model:
            raise ValueError("host, port (1..65535), timeout, and model must be valid")
        self.host, self.port, self.timeout, self.model = host, port, timeout, model.upper()
        self._socket: socket.socket | None = None
        self._scpi: ScpiProtocol | None = None

    def ping(self) -> bool:
        return NetworkHelper.ping(self.host, timeout=self.timeout)

    def connect(self, *, check_ping: bool = True) -> None:
        """Connect and verify the configured RIGOL model with ``*IDN?``."""
        if self._socket is not None:
            return
        if check_ping and not self.ping():
            raise ConnectionError(f"Oscilloscope does not respond to ping: {self.host}")
        self._socket = socket.create_connection((self.host, self.port), self.timeout)
        self._scpi = ScpiProtocol(self._socket)
        try:
            identity = self._query_connected("*IDN?").upper()
            if "RIGOL" not in identity or self.model not in identity:
                raise ConnectionError(f"Expected RIGOL {self.model}; received {identity}")
        except BaseException:
            self.close()
            raise

    def disconnect(self) -> None:
        self.close()

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._scpi = None

    def command(self, scpi: str) -> None:
        if not scpi.strip():
            raise ValueError("SCPI command must not be empty")
        self.connect()
        self._scpi.command(scpi)

    def query(self, scpi: str) -> str:
        if not scpi.strip().endswith("?"):
            raise ValueError("SCPI query must end with '?'")
        self.connect()
        return self._query_connected(scpi)

    def _query_connected(self, scpi: str) -> str:
        return self._scpi.query(scpi)

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
        self._scpi.command(":DISP:DATA? ON,OFF,PNG")
        if self._scpi.read_exactly(1) != b"#":
            raise ValueError("Invalid screenshot response header")
        width = int(self._scpi.read_exactly(1))
        length = int(self._scpi.read_exactly(width))
        image = self._scpi.read_exactly(length)
        self._scpi.read_exactly(1)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image)
        return target

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
