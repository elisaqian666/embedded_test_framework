import subprocess
from unittest.mock import Mock

import pytest

from embedded_test_framework.helpers.he_host_pc import SystemHelper
from embedded_test_framework.helpers.he_network import NetworkHelper


@pytest.mark.parametrize("windows", [False, True])
def test_ping_uses_platform_function_and_correct_command(windows, monkeypatch):
    monkeypatch.setattr(SystemHelper, "is_os_windows", lambda: windows)
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "0% loss", ""))
    monkeypatch.setattr(subprocess, "run", run)

    assert NetworkHelper.ping("192.0.2.1", packets=2, timeout=1)
    expected = ["ping", "-n", "2", "-w", "1000", "192.0.2.1"] if windows else ["ping", "-c", "2", "192.0.2.1"]
    assert run.call_args.args[0] == expected
    assert NetworkHelper.check_ping_status("192.0.2.1", packets=2)
    assert run.call_args.args[0] == ["ping", "-n" if windows else "-c", "2", "192.0.2.1"]


def test_ping_timeout_returns_false(monkeypatch):
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("ping", 1)))
    assert not NetworkHelper.ping("192.0.2.1")
