"""Text conversion shared by communication engines."""


def decode_to_str_if_byte(value: str | bytes) -> str:
    """Decode device output, replacing malformed UTF-8 bytes."""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
