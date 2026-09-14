import pytest

from embedded_test_framework import Device, Registry, DeviceFactory, CapabilityError, ConfigurationError, CommandFailed
from embedded_test_framework.dut.device_features import NetworkCapability
from embedded_test_framework.engine import MemoryTransport, CommandResult
from embedded_test_framework.dut.services import NetworkService, SSHShellService


class JsonNetwork(NetworkCapability):
    """External product adapter using a different command and data format."""
    def get_ipv4_addresses(self, interface="eth0", *, timeout=None):
        import json
        result = self.device.execute("network-json", timeout=timeout).check()
        return json.loads(result.stdout).get(interface, [])


def test_portable_service_works_with_external_adapter():
    registry = Registry.defaults()
    registry.register_capability("json-network", JsonNetwork)
    device = DeviceFactory(registry).create("mcu", {
        "channels": {"shell": {"type": "memory", "responses": {"network-json": '{"wlan0": ["10.0.0.5"]}'}}},
        "capabilities": {"network": {"type": "json-network"}}})
    with device:
        assert NetworkService(device).get_ipv4_addresses("wlan0") == ["10.0.0.5"]


def test_legacy_shell_service_keeps_signature_and_custom_channel():
    with Device("dut", {"ssh": MemoryTransport({"ifconfig eth1": "inet addr:10.0.0.3"})}) as device:
        assert SSHShellService(device, channel="ssh").get_ipv4_addresses("eth1") == ["10.0.0.3"]


def test_missing_capability_and_wrong_owner():
    a, b = Device("a", {"shell": MemoryTransport()}), Device("b", {"shell": MemoryTransport()})
    with pytest.raises(CapabilityError):
        NetworkService(a).get_ipv4_addresses()
    with pytest.raises(CapabilityError):
        a.flash("firmware.bin")
    with pytest.raises(ConfigurationError):
        a.bind_capability("network", JsonNetwork(b))


def test_command_failure_keeps_result_and_legacy_base_class():
    from embedded_test_framework import TransportError
    result = CommandResult("bad", stderr="reason", exit_code=3)
    with pytest.raises(TransportError) as caught:
        result.check()
    assert isinstance(caught.value, CommandFailed)
    assert caught.value.result is result
    assert caught.value.code == "COMMAND_FAILED"


def test_reconnect_does_not_replay_commands():
    transport = MemoryTransport({"write": "ok"})
    with Device("dut", {"shell": transport}) as device:
        device.execute("write")
        device.reconnect()
        assert transport.history == ["write"]
        assert device.connected
