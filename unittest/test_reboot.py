from unittest.mock import Mock

import pytest

from embedded_test_framework import Device, CommandFailed, ConfigurationError
from embedded_test_framework.dut.device_features import HealthCapability, PowerCapability
from embedded_test_framework.engine import MemoryTransport, CommandResult
from embedded_test_framework.libs.errors import DeviceDisconnected, OperationTimeout, TransportError
from embedded_test_framework.dut.services import SSHShellService


BOOT_ID = "cat /proc/sys/kernel/random/boot_id"


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("embedded_test_framework.dut.linux_device.time.monotonic", lambda: now[0])
    monkeypatch.setattr("embedded_test_framework.dut.linux_device.time.sleep",
                        lambda duration: now.__setitem__(0, now[0] + duration))


def make_device(ids, reboot_result=None):
    transport = MemoryTransport()
    values = iter(ids)
    def execute(command, *, timeout=None):
        transport.require_connected()
        transport.history.append(command)
        if command == BOOT_ID:
            return CommandResult(command, stdout=next(values))
        if isinstance(reboot_result, Exception):
            raise reboot_result
        return reboot_result or CommandResult(command)
    transport.execute = Mock(side_effect=execute)
    return Device("dut", {"ssh": transport}).connect(), transport


def test_reboot_waits_for_new_boot_and_health(clock):
    device, transport = make_device(["old", "old", "new", "new"])
    class Health(HealthCapability):
        health_check = Mock(side_effect=[False, True])
    health = Health(device)
    device.bind_capability("health", health)
    with device:
        assert SSHShellService(device, channel="ssh").reboot().exit_code == 0
        assert device.connected
        assert transport.history.count("reboot") == 1
        assert health.health_check.call_count == 2


@pytest.mark.parametrize("result", [DeviceDisconnected("restart"), CommandResult("reboot", exit_code=255),
                                   CommandResult("reboot", exit_code=-1)])
def test_expected_connection_loss_requires_new_boot(clock, result):
    device, transport = make_device(["old", "new"], result)
    with device:
        device.reboot(channel="ssh")
        assert device.connected and transport.connected


def test_reboot_retries_connections_and_restores_timeout(clock):
    device, transport = make_device(["old", "new"])
    connect = transport.connect
    transport.connect = Mock()
    def reconnect():
        if transport.connect.call_count == 1:
            raise TransportError("offline")
        return connect()
    transport.connect.side_effect = reconnect
    with device:
        device.reboot(timeout=2, channel="ssh")
        assert transport.timeout == 5
        assert transport.connect.call_count == 2


def test_unchanged_boot_times_out_and_closes(clock):
    device, transport = make_device(["old"] * 4)
    with pytest.raises(OperationTimeout, match="reboot/check timed out"):
        device.reboot(timeout=2, channel="ssh")
    assert not device.connected and not transport.connected
    assert transport.history.count("reboot") == 1


def test_failed_reboot_is_not_retried(clock):
    device, transport = make_device(["old"], CommandResult("reboot", exit_code=1))
    with device, pytest.raises(CommandFailed):
        device.reboot(channel="ssh")
    assert transport.history == [BOOT_ID, "reboot"]


def test_no_wait_sends_only_reboot_and_invalidates_sessions(clock):
    device, transport = make_device([])
    assert device.reboot(wait_until_reboot=False, channel="ssh").exit_code == 0
    assert transport.history == ["reboot"]
    assert not device.connected and not transport.connected


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf")])
def test_invalid_timeout_does_not_reboot(timeout):
    device, transport = make_device([])
    with device, pytest.raises(ConfigurationError):
        device.reboot(timeout=timeout, channel="ssh")
    assert not transport.history


def test_custom_power_remains_supported():
    class Power(PowerCapability):
        reboot = Mock(return_value="custom")
    device = Device("dut", {"shell": MemoryTransport()})
    power = Power(device)
    device.bind_capability("power", power)
    assert device.reboot() == "custom"
    power.reboot.assert_called_once_with()
