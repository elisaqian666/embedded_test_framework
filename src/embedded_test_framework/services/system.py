"""Reusable system workflows through device APIs."""
from ..logging import get_logger, log_operation


class SystemService:
    def __init__(self, device, *, channel="shell"):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel

    @log_operation
    def version(self, command="cat /etc/os-release", *, timeout=None):
        return self.device.execute(command, channel=self.channel, timeout=timeout).check().stdout.strip()
