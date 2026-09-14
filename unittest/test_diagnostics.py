import json

import pytest

from embedded_test_framework import Device, TransportError
from embedded_test_framework.capabilities import LoggingCapability, CrashCapability, PerformanceCapability
from embedded_test_framework.diagnostics import EvidenceCollector, PerformanceMonitor
from embedded_test_framework.engine import MemoryTransport


def test_evidence_continues_after_source_failure(tmp_path):
    class Logs(LoggingCapability):
        def collect_logs(self, destination):
            raise TransportError("secret details must not appear in manifest")
    class Crash(CrashCapability):
        def detect_crash(self):
            return True
    with Device("board/../../untrusted-name", {"shell": MemoryTransport()}) as device:
        device.bind_capability("logging", Logs(device))
        device.bind_capability("crash", Crash(device))
        artifact = EvidenceCollector().collect({device.name: device}, tmp_path)
    from pathlib import Path
    text = Path(artifact.path).read_text()
    assert "secret details" not in text
    entries = json.loads(text)
    assert entries[0]["status"] == "failed"
    assert entries[0]["error_code"] == "TRANSPORT_ERROR"
    assert entries[1]["detected"] is True
    assert Path(artifact.path).is_relative_to(tmp_path)


def test_performance_records_samples_and_trend(tmp_path, monkeypatch):
    from embedded_test_framework import diagnostics
    now = [0]
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(diagnostics.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))
    class Metrics(PerformanceCapability):
        def sample(self):
            return {"memory_bytes": now[0] * 100}
    with Device("dut", {"shell": MemoryTransport()}) as device:
        device.bind_capability("performance", Metrics(device))
        monitor = PerformanceMonitor(device)
        samples = monitor.record(duration=2, interval=1, destination=tmp_path / "metrics.jsonl")
    assert len(samples) == 3
    assert monitor.trend(samples, "memory_bytes")["delta"] == 200
    assert len((tmp_path / "metrics.jsonl").read_text().splitlines()) == 3


def test_ssh_disconnected_session_and_ftp_timeout(monkeypatch, tmp_path):
    from unittest.mock import Mock, patch
    from embedded_test_framework.engine import SSHTransport, FTPTransport
    from embedded_test_framework import DeviceDisconnected, OperationTimeout
    ssh = SSHTransport("board")
    ssh.connected = True
    ssh._client = Mock()
    ssh._client.get_transport.return_value = None
    with pytest.raises(DeviceDisconnected):
        ssh.execute("version")
    assert not ssh.connected
    ssh.close()
    client = Mock()
    client.retrbinary.side_effect = TimeoutError()
    with patch("embedded_test_framework.engine.ftp.FTP", return_value=client):
        with FTPTransport("board") as ftp:
            with pytest.raises(OperationTimeout):
                ftp.download("logs", tmp_path / "logs")
