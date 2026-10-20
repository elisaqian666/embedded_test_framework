"""Base exceptions used by the generic embedded-device framework."""


def append_string_to_exception_message(exception: Exception, message: str) -> None:
    """Append diagnostic text to an exception without replacing its type."""
    if len(exception.args) >= 1:
        exception.args = (str(exception.args[0]) + "\n" + message,) + exception.args[1:]
    else:
        exception.args = (message,)


class EmbeddedFrameworkException(Exception):
    """Base exception for framework operations."""


class EmbeddedFrameworkRuntimeError(RuntimeError):
    """Runtime failure in a generic operation."""
    pass

class EmbeddedSetupException(EmbeddedFrameworkException):
    pass

class EmbeddedConfiguratorError(EmbeddedFrameworkException):
    pass


class ADBCommandInvocationError(EmbeddedFrameworkRuntimeError):
    """ADB command failed, timed out, or could not be started."""
    pass


class SSHCommandError(EmbeddedFrameworkRuntimeError):
    """SSH command failed, timed out, or lost its connection."""
    pass


class EmbeddedFrameworkSetupError(EmbeddedFrameworkException):
    """Invalid runtime configuration or setup."""
    pass

class DeviceCrashFound(ValueError):
    def __init__(self, coredump_names: list[str] | None = None):
        coredump_names = coredump_names or []
        message = f"Coredumps(s) found on the device: {', '.join(coredump_names)}"
        super().__init__(message)

class FeatureNotSupportedError(EmbeddedFrameworkException):
    pass