from embedded_test_framework.devices.base import BaseDevice, Capability
from embedded_test_framework.helpers.he_linux_host import LinuxHelper
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.protocols.can import CanProtocol
from embedded_test_framework.protocols.mqtt import MqttProtocol


class LinuxDevice(BaseDevice):
    """Bind Linux operations to configured connections owned by BaseDevice."""

    connection_capabilities = {
        Capability.SHELL: frozenset({"ssh"}),
        Capability.MQTT: frozenset({"mqtt"}),
        Capability.CAN: frozenset({"can"}),
    }

    def can(self, connection: str | None = None) -> CanProtocol:
        return CanProtocol(self.engine(connection, protocol="can"))

    def linux_host(self, connection: str | None = None) -> LinuxHelper:
        return LinuxHelper(self.engine(connection, protocol="ssh"))

    def mqtt(self, connection: str | None = None) -> MqttProtocol:
        return MqttProtocol(self.engine(connection, protocol="mqtt"))

    def service(self, name: str, action: str, *, connection: str | None = None, timeout: float | None = None) -> CommandResult:
        return self.linux_host(connection).service(name, action, timeout=timeout)

    def execute(self, command: str, timeout: float | None = None, *, connection: str | None = None, check: bool = True) -> CommandResult:
        return self.linux_host(connection).execute(command, timeout=timeout, check=check)

    shell = execute
