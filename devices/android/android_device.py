"""Android DUT adapter."""

from embedded_test_framework.devices.base import BaseDevice, Capability
from embedded_test_framework.helpers.he_android import AndroidHelper
from embedded_test_framework.lib.command_result import CommandResult


class AndroidDevice(BaseDevice):
    """Bind Android operations to configured ADB clients owned by BaseDevice."""

    connection_capabilities = {Capability.ADB: frozenset({"adb"}), Capability.SHELL: frozenset({"adb"})}

    def adb(self, connection: str | None = None) -> AndroidHelper:
        return AndroidHelper(self.engine(connection, protocol="adb"))

    def execute(self, command: str, timeout: float | None = None, *, connection: str | None = None, check: bool = True) -> CommandResult:
        return self.adb(connection).shell(command, timeout=timeout, check=check)

    shell = execute
