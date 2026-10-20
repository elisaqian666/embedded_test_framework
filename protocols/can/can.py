"""Classical CAN frame operations over an injected python-can compatible client."""

import math
from typing import Any


class CanProtocol:
    """Send standard/extended data frames; the caller owns the client lifecycle."""

    def __init__(self, client: Any) -> None:
        if not all(callable(getattr(client, name, None)) for name in ("send", "recv")):
            raise TypeError("CAN requires a client with send and recv methods")
        self.client = client

    @staticmethod
    def _timeout(timeout: float) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("CAN timeout must be a finite non-negative number")

    def send(self, arbitration_id: int, data: bytes = b"", *, is_extended_id: bool = False, timeout: float = 10) -> None:
        """Send up to eight data bytes; backend send errors propagate unchanged."""
        self._timeout(timeout)
        if type(is_extended_id) is not bool:
            raise TypeError("CAN is_extended_id must be a bool")
        if type(arbitration_id) is not int:
            raise ValueError("CAN arbitration_id must be an integer")
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("CAN data must be bytes or bytearray")
        import can

        message = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id, check=True)
        self.client.send(message, timeout=timeout)

    def receive(self, timeout: float = 10) -> Any:
        """Return a native can.Message, or raise TimeoutError when no frame arrives."""
        self._timeout(timeout)
        message = self.client.recv(timeout=timeout)
        if message is None:
            raise TimeoutError("Timed out waiting for CAN frame")
        return message
