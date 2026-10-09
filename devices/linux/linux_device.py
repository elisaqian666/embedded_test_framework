import shlex

from embedded_test_framework.devices.base import BaseDevice, Capability, DeviceStateError
from embedded_test_framework.helpers.he_shell import CommandResult, ShellHelper
from embedded_test_framework.protocols.mqtt import MqttProtocol


class LinuxDevice(BaseDevice):
    """Linux adapter with service management through its shell connection."""

    capabilities = frozenset({Capability.SHELL})
    connection_capabilities = {Capability.MQTT: frozenset({"mqtt"})}

    def execute(self, command: str, timeout: float = 30, *, connection: str | None = None, check: bool = True) -> CommandResult:
        if timeout <= 0:
            raise ValueError("Command timeout must be positive")
        execute = getattr(self.engine(connection), "do_command_w_exitstatus", None)
        if not callable(execute):
            raise DeviceStateError("The selected connection does not support shell commands")
        stdout, status, stderr = execute(command, time_out=timeout)
        result = CommandResult(stdout, status, stderr)
        return result.check() if check else result

    def shell(self, connection: str | None = None) -> ShellHelper:
        return ShellHelper(self.engine(connection))

    def mqtt(self, connection: str = "mqtt") -> MqttProtocol:
        self.require(Capability.MQTT)
        return MqttProtocol(self.engine(connection))

    def service(self, name: str, action: str, *, timeout: float = 30) -> CommandResult:
        self.require(Capability.SHELL)
        if not name or action not in {"start", "stop", "restart", "status"}:
            raise ValueError("service name and action must be valid")
        return self.execute(f"systemctl {action} {shlex.quote(name)}", timeout=timeout, check=action != "status")
