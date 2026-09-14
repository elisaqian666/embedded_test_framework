"""
Purpose: This module contains helper functions to create a qr code
"""
from pathlib import Path
from ..libs.errors import ConfigurationError


def create_qr_code(text, destination):
    """Create a PNG QR code using the optional qrcode dependency."""
    if not isinstance(text, str) or not text:
        raise ConfigurationError("QR code text must be a nonempty string")
    path = Path(destination)
    if path.suffix.lower() != ".png":
        raise ConfigurationError("QR code destination must use the .png extension")
    try:
        import qrcode
    except ImportError as exc:
        raise ConfigurationError("Install embedded-test-framework[qr] for QR code generation") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(text).save(path, format="PNG")
    return path
