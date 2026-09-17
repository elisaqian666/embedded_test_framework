"""Base exceptions used by the generic embedded-device framework."""


def append_string_to_exception_message(exception: Exception, message: str) -> None:
    """Append diagnostic text to an exception without replacing its type."""
    exception.args = ((str(exception.args[0]) + "\n" if exception.args else "") + message, *exception.args[1:])


class EmbeddedFrameworkException(Exception):
    """Base exception for framework operations."""


class EmbeddedFrameworkRuntimeError(RuntimeError):
    """Runtime failure in a generic operation."""


class EmbeddedFrameworkSetupError(EmbeddedFrameworkException):
    """Invalid runtime configuration or setup."""
