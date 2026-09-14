"""Shell commands and IPv4 discovery through a device's SSH channel."""

from ipaddress import IPv4Address
import re

from ..errors import ConfigurationError
from ..logging import get_logger, log_operation


class SSHShellService:
    """Reuse a connected Device; configure its selected channel as SSHTransport."""

    def __init__(self, device, *, channel="shell"):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel

    @log_operation
    def execute(self, command, *, timeout=None):
        """Return CommandResult; call check() to raise on a nonzero exit code."""
        return self.device.execute(command, channel=self.channel, timeout=timeout)

    @log_operation
    def get_ipv4_addresses(self, interface="eth0", *, command="ifconfig", include_loopback=False, timeout=None):
        """Return unique IPv4 strings in output order, or [] if none are found.

        Query eth0 by default; pass another interface or None for all interfaces.
        Command must be `ifconfig` or `ip -4 addr`. Command
        failures raise TransportError. The caller owns the device lifecycle.
        """
        if command not in ("ifconfig", "ip -4 addr"):
            raise ConfigurationError("command must be 'ifconfig' or 'ip -4 addr'")
        if interface is not None:
            if not isinstance(interface, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.:-]*", interface):
                raise ConfigurationError("Invalid network interface name")
            command += (" dev " if command == "ip -4 addr" else " ") + interface
        output = self.execute(command, timeout=timeout).check().stdout
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
