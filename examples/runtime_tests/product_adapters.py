"""Example consumer-owned adapters. No imports from communication implementations."""
import json
from pathlib import Path

from embedded_test_framework.capabilities import NetworkCapability, LoggingCapability, PerformanceCapability
from embedded_test_framework.lab import Helper


class JsonNetwork(NetworkCapability):
    def get_ipv4_addresses(self, interface="eth0", *, timeout=None):
        result = self.device.execute("network status --json", timeout=timeout).check()
        return json.loads(result.stdout).get(interface, [])


class BoardLogs(LoggingCapability):
    def collect_logs(self, destination):
        result = self.device.execute("read-test-logs", timeout=5).check()
        path = Path(destination) / "board.log"
        path.write_text(result.stdout, encoding="utf-8")
        return path


class BoardMetrics(PerformanceCapability):
    def sample(self):
        result = self.device.execute("read-test-metrics", timeout=5).check()
        return json.loads(result.stdout)


class SimulatedLab(Helper):
    """Offline example only. A real vendor plugin implements its own preparation."""
    def __init__(self, context):
        self.context = context
        self.ready = False

    def prepare(self):
        self.ready = True

    def cleanup(self):
        self.ready = False


def register(registry):
    registry.register_capability("example-json-network", JsonNetwork)
    registry.register_capability("example-logs", BoardLogs)
    registry.register_capability("example-metrics", BoardMetrics)
    registry.register_helper("example-lab", SimulatedLab)
