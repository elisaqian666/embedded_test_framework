"""Linux/BusyBox shell adapter; no shell syntax is embedded in generic services."""
from ipaddress import IPv4Address
import re
import time
from ..dut.device_features import NetworkCapability, PowerCapability
from ..dut import Device
from ..libs.errors import ConfigurationError, TransportError, DeviceDisconnected, OperationTimeout
from ..libs.contracts import CommandChannel
from ..libs.validation import positive_timeout
from ..libs.logging import get_logger, log_operation


class LinuxNetworkCapability(NetworkCapability):
    def __init__(self, device, *, channel="shell", command="ifconfig"):
        super().__init__(device)
        self.channel = channel
        if command not in ("ifconfig", "ip -4 addr"):
            raise ConfigurationError("Unsupported address query command")
        self.command = command
        self.logger = get_logger("dut", type(self).__name__)

    @log_operation
    def get_ipv4_addresses(self, interface="eth0", *, command=None, include_loopback=False, timeout=None):
        """Return unique IPv4 strings in output order, or [] if none are found.

        Query eth0 by default; pass another interface or None for all interfaces.
        Command must be `ifconfig` or `ip -4 addr`. Command
        failures raise TransportError. The caller owns the device lifecycle.
        """
        command = self.command if command is None else command
        if command not in ("ifconfig", "ip -4 addr"):
            raise ConfigurationError("command must be 'ifconfig' or 'ip -4 addr'")
        if interface is not None:
            if not isinstance(interface, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.:-]*", interface):
                raise ConfigurationError("Invalid network interface name")
            command += (" dev " if command == "ip -4 addr" else " ") + interface
        output = self.device.execute(command, channel=self.channel, timeout=timeout).check().stdout
        addresses = []
        for value in re.findall(r"\binet\s+(?:addr:\s*)?([0-9.]+)(?=[/\s]|$)", output):
            try:
                address = IPv4Address(value)
            except ValueError:
                continue
            if address.is_unspecified or (address.is_loopback and not include_loopback):
                continue
            value = str(address)
            if value not in addresses:
                addresses.append(value)
        return addresses


class LinuxPowerCapability(PowerCapability):
    """Confirm reboot by boot ID, then check all channels and optional health.

    Transport connect timeouts are capped to the remaining budget. Custom
    health checks must enforce their own I/O timeouts.
    """
    def __init__(self, device, *, channel="shell"):
        super().__init__(device)
        self.channel = channel

    def reboot(self, timeout=60, wait_until_reboot=True, *, interval=1.0):
        timeout = positive_timeout(timeout)
        interval = positive_timeout(interval)
        if not isinstance(wait_until_reboot, bool):
            raise ConfigurationError("wait_until_reboot must be a boolean")
        self.device.channel(self.channel, CommandChannel)
        deadline = time.monotonic() + timeout

        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise OperationTimeout(f"Device {self.device.name!r} reboot/check timed out")
            return value

        def boot_id():
            value = self.device.execute("cat /proc/sys/kernel/random/boot_id",
                                        channel=self.channel, timeout=remaining()).check().stdout.strip()
            if not value:
                raise TransportError("Device returned an empty boot ID")
            return value

        previous = boot_id() if wait_until_reboot else None
        result = None
        try:
            result = self.device.execute("reboot", channel=self.channel, timeout=remaining())
            # OpenSSH uses 255 on connection loss; Paramiko may report -1.
            if not wait_until_reboot or result.exit_code not in (255, -1):
                result.check()
        except DeviceDisconnected:
            if not wait_until_reboot:
                self.device.close()
                raise
        self.device.close()
        if not wait_until_reboot:
            return result

        last_error = None
        while True:
            try:
                remaining()
            except OperationTimeout as exc:
                raise exc from last_error
            try:
                # Reopen every channel, since all sessions may be stale.
                for transport in self.device._channels.values():
                    original = transport.timeout
                    try:
                        transport.timeout = min(original, remaining())
                        transport.connect()
                    finally:
                        transport.timeout = original
                self.device.connected = True
                if boot_id() != previous:
                    healthy = (self.device.health_check()
                               if "health" in self.device.capabilities else True)
                    remaining()
                    if healthy:
                        return result
            except TransportError as exc:
                last_error = exc
            except Exception:
                self.device.close()
                raise
            self.device.close()
            time.sleep(min(interval, max(0, deadline - time.monotonic())))


class LinuxDevice(Device):
    def __init__(self, name, channels, *, metadata=None, host=None):
        super().__init__(name, channels, metadata=metadata, host=host)
        self.bind_capability("network", LinuxNetworkCapability(self))
