"""Common Android Debug Bridge operations."""

import logging
from enum import Enum, unique

from embedded_test_framework.communication.adb import AdbClient
from embedded_test_framework.configurator.config_labels import LOGGERS
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import ADBCommandInvocationError


@unique
class LogLevel(Enum):
    VERBOSE = "V"
    DEBUG = "O"
    INFO = "I"
    WARN = "W"
    ERROR = "E"
    FATAL = "F"


@unique
class LogBuffer(Enum):
    DEFAULT = "default"
    RADIO = "radio"
    EVENTS = "events"
    MAIN = "main"
    CRASH = "crash"
    KERNEL = "kernel"
    SECURITY = "security"
    SYSTEM = "system"
    ALL = "all"


class AndroidHelper:
    """Convenience operations for an already-connected ADB client."""

    def __init__(self, adb: AdbClient) -> None:
        if not callable(getattr(adb, "command", None)) or not callable(getattr(adb, "shell", None)):
            raise TypeError("AndroidHelper requires an ADB client")
        self.adb = adb
        self.logger = logging.getLogger(LOGGERS.HELPER)

    def shell(self, command: str, *, timeout: float | None = None, check: bool = True) -> CommandResult:
        if type(check) is not bool:
            raise TypeError("check must be bool")
        result = self.adb.shell(command, timeout=timeout)
        return result.check(ADBCommandInvocationError) if check else result

    execute = shell

    def command(self, *args: str, timeout: float | None = None, check: bool = True) -> CommandResult:
        """Run explicit ADB arguments; device selection remains in configuration."""
        if type(check) is not bool:
            raise TypeError("check must be bool")
        result = self.adb.command(*args, timeout=timeout)
        return result.check(ADBCommandInvocationError) if check else result

    def logcat(self, *args: str, timeout: float | None = None, check: bool = True) -> CommandResult:
        """Return a one-shot logcat dump; optional arguments are passed to logcat."""
        return self.command("logcat", "-d", *args, timeout=timeout, check=check)

    def bugreport(self, *, timeout: float | None = None, check: bool = True) -> CommandResult:
        return self.command("bugreport", timeout=timeout, check=check)

    logreport = bugreport
