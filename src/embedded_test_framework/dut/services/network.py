"""Portable network operations, independent of SSH/REST/serial implementation."""
from ...dut.device_features import NetworkCapability
from ...libs.logging import get_logger, log_operation


class NetworkService:
    def __init__(self, device):
        self.device = device
        self.logger = get_logger("server", type(self).__name__)

    @log_operation
    def get_ipv4_addresses(self, interface="eth0", *, timeout=None):
        return self.device.capability("network", NetworkCapability).get_ipv4_addresses(interface, timeout=timeout)
