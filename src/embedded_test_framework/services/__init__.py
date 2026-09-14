from ..logging import get_logger, log_operation
"""Reusable workflows. Product commands and expected values belong to consumers."""
import time
from .host import HostService
from .ssh_shell import SSHShellService

from ..errors import OperationTimeout, TransportError
from ..engine.transport_base import positive_timeout


class SystemService:
    def __init__(self, device, *, channel="shell"):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel

    @log_operation
    def version(self, command="cat /etc/os-release", *, timeout=None):
        return self.device.execute(command, channel=self.channel, timeout=timeout).check().stdout.strip()


class HealthService:
    def __init__(self, device, *, channel="api", path="/health", expected_status=200):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel
        self.path, self.expected_status = path, expected_status

    @log_operation
    def check(self, *, timeout=None):
        return self.device.request("GET", self.path, channel=self.channel, timeout=timeout).status_code == self.expected_status

    @log_operation
    def wait_ready(self, *, timeout=30.0, interval=0.5):
        deadline = time.monotonic() + positive_timeout(timeout)
        positive_timeout(interval)
        last_error = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OperationTimeout("Device health did not become ready") from last_error
            try:
                if self.check(timeout=remaining):
                    return
            except TransportError as exc:
                last_error = exc
            time.sleep(min(interval, max(0, deadline - time.monotonic())))


class FileService:
    def __init__(self, device, *, channel="files"):
        self.logger = get_logger("server", type(self).__name__)
        self.device, self.channel = device, channel

    @log_operation
    def download(self, remote_path, local_path):
        return self.device.download(remote_path, local_path, channel=self.channel)

    @log_operation
    def upload(self, local_path, remote_path):
        return self.device.upload(local_path, remote_path, channel=self.channel)


__all__ = ["SystemService", "HealthService", "FileService", "HostService", "SSHShellService"]
