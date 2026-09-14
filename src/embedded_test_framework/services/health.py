"""Reusable health workflows through device APIs."""
from ..logging import get_logger, log_operation
import time
from ..errors import OperationTimeout, TransportError
from ..core.validation import positive_timeout


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
