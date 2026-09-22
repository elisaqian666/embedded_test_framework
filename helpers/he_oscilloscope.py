"""Minimal LAN/SCPI control for RIGOL oscilloscopes."""

import argparse
import socket


class RigolOscilloscope:
    """Control a RIGOL oscilloscope through its SCPI TCP service."""

    def __init__(self, host: str, port: int = 5555, timeout: float = 5) -> None:
        if not host or not 1 <= port <= 65535 or timeout <= 0:
            raise ValueError("host, port (1..65535), and timeout must be valid")
        self.host, self.port, self.timeout = host, port, timeout

    def command(self, scpi: str) -> None:
        """Send one SCPI command."""
        if not scpi.strip():
            raise ValueError("SCPI command must not be empty")
        with socket.create_connection((self.host, self.port), self.timeout) as connection:
            connection.sendall((scpi.rstrip("\r\n") + "\n").encode())

    def query(self, scpi: str) -> str:
        """Send one SCPI query and return its response."""
        if not scpi.strip().endswith("?"):
            raise ValueError("SCPI query must end with '?'")
        with socket.create_connection((self.host, self.port), self.timeout) as connection:
            connection.sendall((scpi.rstrip("\r\n") + "\n").encode())
            return connection.recv(4096).decode().strip()

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Control a RIGOL oscilloscope over LAN SCPI")
    parser.add_argument("host", help="oscilloscope IP address or hostname")
    parser.add_argument("action", choices=("idn", "run", "stop", "single", "autoscale", "command", "query"))
    parser.add_argument("scpi", nargs="?", help="SCPI text for command/query actions")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    scope = RigolOscilloscope(args.host, args.port, args.timeout)
    if args.action in {"command", "query"} and not args.scpi:
        parser.error("scpi is required for command and query")
    method = getattr(scope, {"idn": "identify"}.get(args.action, args.action))
    result = method(args.scpi) if args.scpi else method()
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
