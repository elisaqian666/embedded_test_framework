"""Android DUT adapter."""

from embedded_test_framework.devices.base import BaseDevice, Capability, DeviceStateError
from embedded_test_framework.helpers.he_android import AndroidHelper
from embedded_test_framework.helpers.he_shell import CommandResult


class AndroidDevice(BaseDevice):
    """Android adapter exposing ADB shell commands."""

    capabilities = frozenset({Capability.ADB})

    def adb(self, connection: str | None = None) -> AndroidHelper:
        self.require(Capability.ADB)
        return AndroidHelper(self.engine(connection))

    def execute(self, command: str, timeout: float = 30, *, connection: str | None = None, check: bool = True) -> CommandResult:
        if timeout <= 0:
            raise ValueError("Command timeout must be positive")
        shell = getattr(self.engine(connection), "shell", None)
        if not callable(shell):
            raise DeviceStateError("The selected connection does not support ADB shell commands")
        result = shell(command, timeout=timeout)
        return result.check() if check else result
