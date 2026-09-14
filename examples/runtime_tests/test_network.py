from embedded_test_framework import wait
from embedded_test_framework.helpers.evidence import PerformanceMonitor


def test_networks(test_context):
    assert test_context.helpers["lab"].ready
    assert test_context.services["dut_network"].get_ipv4_addresses() == ["192.0.2.10"]
    assert test_context.services["peer_network"].get_ipv4_addresses() == ["192.0.2.11"]


def test_network_ready(test_context):
    addresses = wait.until_true(test_context.services["dut_network"].get_ipv4_addresses, timeout=1)
    assert addresses == ["192.0.2.10"]


def test_metrics_and_evidence(test_context, tmp_path):
    monitor = PerformanceMonitor(test_context.devices["dut"])
    samples = monitor.record(duration=.02, interval=.01, destination=tmp_path / "metrics.jsonl")
    assert monitor.trend(samples, "memory_bytes")["delta"] == 0
    artifact = test_context.collect_evidence(tmp_path)
    assert artifact.kind == "evidence-manifest"
