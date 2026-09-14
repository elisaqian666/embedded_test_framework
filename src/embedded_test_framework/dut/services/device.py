"""Portable DUT workflows; unsupported operations report CapabilityError."""
from ...libs.logging import get_logger, log_operation
from ... import wait
from ...libs.errors import TransportError


class DeviceService:
    def __init__(self, device):
        self.device = device
        self.logger = get_logger("server", type(self).__name__)

    @log_operation
    def reboot(self, timeout=60, wait_until_reboot=True):
        return self.device.reboot(timeout=timeout, wait_until_reboot=wait_until_reboot)

    @log_operation
    def flash(self, image):
        return self.device.flash(image)

    @log_operation
    def wait_ready(self, *, timeout=30.0, interval=0.5):
        return wait.until_true(self.device.health_check, timeout=timeout, interval=interval,
                               exceptions=(TransportError,))

    @log_operation
    def collect_logs(self, destination):
        return self.device.collect_logs(destination)

    @log_operation
    def detect_crash(self):
        return self.device.detect_crash()
