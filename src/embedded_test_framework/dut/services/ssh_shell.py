"""Backward-compatible shell service; device adapters own platform parsing."""
from ...libs.logging import get_logger, log_operation


class SSHShellService:
    """Reuse a connected Device; configure its selected channel as SSHTransport."""
    def __init__(self, device, *, channel="shell"):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel

    @log_operation
    def execute(self, command, *, timeout=None):
        return self.device.execute(command, channel=self.channel, timeout=timeout)

    @log_operation
    def get_ipv4_addresses(self, interface="eth0", *, command="ifconfig", include_loopback=False, timeout=None):
        return self.device.get_ipv4_addresses(interface, channel=self.channel, command=command,
                                              include_loopback=include_loopback, timeout=timeout)

    @log_operation
    def reboot(self, timeout=60, wait_until_reboot=True):
        return self.device.reboot(timeout=timeout, wait_until_reboot=wait_until_reboot,
                                  channel=self.channel)
    
