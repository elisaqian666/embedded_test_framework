"""Linux/BusyBox shell adapter; no shell syntax is embedded in generic services."""
from ipaddress import IPv4Address
import re
from ..capabilities import NetworkCapability
from ..devices import Device
from ..errors import ConfigurationError
from ..logging import get_logger, log_operation


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


class LinuxDevice(Device):
    def __init__(self, name, channels, *, metadata=None, host=None):
        super().__init__(name, channels, metadata=metadata, host=host)
        self.bind_capability("network", LinuxNetworkCapability(self))
