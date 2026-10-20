"""Command framing for an existing serial transport; connection ownership stays with the DUT."""

from typing import Any


class SerialHelper:
    """Send text commands or binary frames through SerialTransport.write()."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def send_command(
        self, command: str | bytes, *, hex_mode: bool = False, eol: str | bytes = b"", encoding: str = "utf-8"
    ) -> int:
        """Send once and return the byte count, including the optional terminator.

        hex_mode accepts hexadecimal text such as 'AA 01 FF' or 'AA01FF',
        without 0x prefixes. Text uses encoding; bytes are sent unchanged.
        eol may be '', '\\r', '\\n', '\\r\\n', or custom terminator bytes.
        No terminator, buffer clearing, retry, or response read is implicit.
        """
        if not isinstance(command, (str, bytes)):
            raise TypeError("command must be str or bytes")
        if not isinstance(hex_mode, bool):
            raise TypeError("hex_mode must be bool")
        if not isinstance(eol, (str, bytes)):
            raise TypeError("eol must be str or bytes")
        if hex_mode:
            if not isinstance(command, str):
                raise TypeError("hex_mode requires hexadecimal text")
            data = bytes.fromhex(command)
        else:
            data = command.encode(encoding) if isinstance(command, str) else command
        terminator = eol.encode(encoding) if isinstance(eol, str) else eol
        frame = data + terminator
        if not frame:
            raise ValueError("command and eol cannot both be empty")
        written = self.engine.write(frame)
        if written != len(frame):
            # Retrying could execute a non-idempotent device command twice.
            raise OSError(f"Incomplete serial write: {written!r} of {len(frame)} bytes; device may have received a partial command")
        return written
