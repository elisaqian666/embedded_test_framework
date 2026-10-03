"""Common Android Debug Bridge operations."""

from embedded_test_framework.communication.adb import AdbClient
from embedded_test_framework.helpers.he_shell import CommandResult


class AndroidHelper:
    """Convenience operations for an already-connected ADB client."""

    def __init__(self, adb: AdbClient) -> None:
        if not callable(getattr(adb, "command", None)) or not callable(getattr(adb, "shell", None)):
            raise TypeError("AndroidHelper requires an ADB client")
        self.adb = adb

    def shell(self, command: str, *, timeout: float = 30, check: bool = True) -> CommandResult:
        result = self.adb.shell(command, timeout=timeout)
        return result.check() if check else result

    def logcat(self, *args: str, timeout: float = 30, check: bool = True) -> CommandResult:
        """Return a one-shot logcat dump; optional arguments are passed to logcat."""
        result = self.adb.command("logcat", "-d", *args, timeout=timeout)
        return result.check() if check else result

    def bugreport(self, *, timeout: float = 120, check: bool = True) -> CommandResult:
        result = self.adb.command("bugreport", timeout=timeout)
        return result.check() if check else result

    logreport = bugreport
