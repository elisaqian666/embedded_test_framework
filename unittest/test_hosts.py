import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from embedded_test_framework import Device, DeviceFactory, LocalHost, Peripheral, ConfigurationError, OperationTimeout
from embedded_test_framework.hosts import ProcessInfo
from embedded_test_framework.services import HostService
from embedded_test_framework.engine import MemoryTransport


def test_run_real_command_and_timeout():
    host = LocalHost()
    result = host.run([sys.executable, "-c", "print('host-ready')"])
    assert result.ok and result.stdout.strip() == "host-ready"
    assert host.run([sys.executable, "-c", "raise SystemExit(7)"]).exit_code == 7
    with pytest.raises(OperationTimeout):
        host.run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.05)
    with pytest.raises(ConfigurationError):
        host.run("echo unsafe")


def test_owned_application_is_stopped():
    with LocalHost() as host:
        app = host.start_application([sys.executable, "-c", "import time; time.sleep(60)"])
        assert app.running and app.pid > 0
    assert not app.running
    host.close()


def test_windows_spawn_hidden_by_default():
    import os
    if os.name != "nt":
        pytest.skip("Windows creation flags")
    with patch("embedded_test_framework.hosts.local.subprocess.Popen") as popen:
        host = LocalHost()
        host.start_application(["tool.exe"])
        assert popen.call_args.kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
        host.start_application(["tool.exe"], visible=True)
        assert "creationflags" not in popen.call_args.kwargs


def test_peripheral_matching_and_wait():
    host = Mock()
    expected = Peripheral("COM3", "Board", "serial", "present", 0x1234, 0x5678, "board-1")
    host.list_peripherals.side_effect = [[], [expected]]
    assert HostService(host).wait_for_peripheral(vid=0x1234, serial_number="board-1", interval=0.001) == expected
    host.list_peripherals.side_effect = None
    host.list_peripherals.return_value = [expected]
    assert not HostService(host).find_peripherals(identifier="COM30")
    with pytest.raises(ConfigurationError):
        HostService(host).find_peripherals()
    with pytest.raises(OperationTimeout):
        HostService(host).wait_for_peripheral(identifier="COM99", timeout=0.001, interval=0.001)


def test_windows_pnp_and_process_queries():
    host = LocalHost()
    with patch("embedded_test_framework.hosts.local.platform.system", return_value="Windows"):
        with patch.object(host, "_powershell_json", return_value=[
            {"InstanceId": "USB\\VID_1234&PID_5678\\ABC", "FriendlyName": "Board", "Status": "OK", "Class": "USB"},
            {"InstanceId": "PCI\\ABC", "FriendlyName": "Other", "Status": "Error", "Class": "PCI"}
        ]):
            devices = host.list_peripherals(kind="usb")
            assert len(devices) == 1 and devices[0].name == "Board"
            assert devices[0].vid == 0x1234 and devices[0].pid == 0x5678
        with patch.object(host, "_powershell_json", return_value=[{"ProcessId": 42, "Name": "Tool.exe"}]):
            assert host.list_processes() == [ProcessInfo(42, "Tool.exe")]
            assert host.is_process_running("tool.EXE")
            assert not host.is_process_running("Tool")


def test_device_host_ownership_and_config():
    shared = LocalHost()
    shared.close = Mock()
    with Device("dut", {"shell": MemoryTransport()}, host=shared) as device:
        assert device.host is shared
    shared.close.assert_not_called()
    device = DeviceFactory().create("dut", {"host": {"type": "local", "name": "bench-1"},
                                            "channels": {"shell": {"type": "memory"}}})
    assert device.host.name == "bench-1"
    device.host.close = Mock()
    device.close()
    device.host.close.assert_called_once()
    with pytest.raises(ConfigurationError):
        DeviceFactory().create("dut", {"host": {"type": "remote"}, "channels": {"shell": {"type": "memory"}}})


def test_connection_failure_closes_owned_host():
    transport = MemoryTransport()
    transport.connect = Mock(side_effect=RuntimeError("offline"))
    device = Device("dut", {"shell": transport})
    device.host.close = Mock()
    with pytest.raises(RuntimeError):
        device.connect()
    device.host.close.assert_called_once()
