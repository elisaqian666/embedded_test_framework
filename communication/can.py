"""CAN connections backed by python-can, imported only when opening a bus."""

from typing import Any


def validate_can_options(interface: str, channel: str | int, bitrate: int = 500000) -> None:
    if not isinstance(interface, str) or not interface.strip():
        raise ValueError("CAN interface must be a non-empty string")
    if not ((isinstance(channel, str) and channel.strip()) or (type(channel) is int and channel >= 0)):
        raise ValueError("CAN channel must be a non-empty string or non-negative integer")
    if type(bitrate) is not int or bitrate <= 0:
        raise ValueError("CAN bitrate must be a positive integer")


class CanClient:
    """Adapt a python-can bus to the framework's close() lifecycle."""

    def __init__(self, bus: Any) -> None:
        self.bus = bus

    def send(self, message: Any, timeout: float = 10) -> None:
        self.bus.send(message, timeout=timeout)

    def recv(self, timeout: float = 10) -> Any:
        return self.bus.recv(timeout=timeout)

    def close(self) -> None:
        self.bus.shutdown()

    def __enter__(self) -> "CanClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def make_can_client(interface: str, channel: str | int, bitrate: int = 500000) -> CanClient:
    """Open a classical CAN bus with explicit backend, channel and bitrate."""
    validate_can_options(interface, channel, bitrate)
    try:
        import can
    except ImportError as error:
        raise ImportError("python-can is required for CAN connections") from error
    return CanClient(can.Bus(interface=interface, channel=channel, bitrate=bitrate, ignore_config=True))
