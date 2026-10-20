from unittest.mock import Mock
from uuid import uuid4

import can
import pytest
from embedded_test_framework.communication.can import make_can_client
from embedded_test_framework.configurator.configurator_dut import ConfigurationError, ConnectionConfig, EngineFactory
from embedded_test_framework.devices import Capability
from embedded_test_framework.protocols.can import CanProtocol
from embedded_test_framework.runtime import Runtime


@pytest.mark.parametrize("kind", ["generic", "linux", "stm32"])
def test_can_configured_roundtrip_and_cleanup(kind):
    channel = uuid4().hex
    options = {"interface": "virtual", "channel": channel, "bitrate": 500000}
    config = {"devices": {"target": {
        "metadata": {"type": kind},
        "connections": {"can": {"protocol": "can", "options": options}},
    }}}
    with make_can_client(**options) as peer, Runtime.from_mapping(config) as runtime:
        dut = runtime.duts["target"]
        client = dut.engine("can")
        protocol = CanProtocol(client) if kind == "generic" else dut.can()
        if kind != "generic":
            assert dut.supports(Capability.CAN)
        for frame_id, extended in [(0, False), (0x7FF, False), (0x1FFFFFFF, True)]:
            protocol.send(frame_id, b"\x00\xff", is_extended_id=extended)
            frame = peer.recv(timeout=0.2)
            assert frame.arbitration_id == frame_id
            assert frame.is_extended_id is extended
            assert frame.data == b"\x00\xff"
            peer.send(frame)
            assert protocol.receive(timeout=0.2).data == frame.data
        with pytest.raises(TimeoutError):
            protocol.receive(timeout=0)
    with pytest.raises(can.CanOperationError):
        client.recv(timeout=0)
    client.close()


@pytest.mark.parametrize("kwargs", [
    {"arbitration_id": -1}, {"arbitration_id": 0x800}, {"arbitration_id": True},
    {"arbitration_id": 0x20000000, "is_extended_id": True},
    {"arbitration_id": 1, "data": b"123456789"},
    {"arbitration_id": 1, "data": 8},
    {"arbitration_id": 1, "is_extended_id": 1},
])
def test_can_invalid_frames_never_reach_bus(kwargs):
    client = Mock()
    with pytest.raises((ValueError, TypeError)):
        CanProtocol(client).send(**kwargs)
    client.send.assert_not_called()


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf"), True, "1", None])
def test_can_invalid_timeouts_never_reach_bus(timeout):
    client = Mock()
    protocol = CanProtocol(client)
    with pytest.raises(ValueError):
        protocol.send(1, timeout=timeout)
    with pytest.raises(ValueError):
        protocol.receive(timeout=timeout)
    client.send.assert_not_called()
    client.recv.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"interface": ""}, {"interface": 1}, {"channel": ""}, {"channel": True},
    {"channel": -1}, {"bitrate": 0}, {"bitrate": True}, {"bitrate": "500000"},
    {"unknown": 1},
])
def test_can_config_rejected_before_open(overrides):
    options = {"interface": "virtual", "channel": "test", **overrides}
    with pytest.raises(ConfigurationError):
        EngineFactory().validate(ConnectionConfig("can", options))


def test_can_backend_errors_propagate_and_client_is_checked():
    with pytest.raises(TypeError):
        CanProtocol(object())
    client = Mock()
    error = can.CanOperationError("bus failed")
    client.send.side_effect = error
    client.recv.side_effect = error
    with pytest.raises(can.CanOperationError) as caught:
        CanProtocol(client).send(1)
    assert caught.value is error
    with pytest.raises(can.CanOperationError):
        CanProtocol(client).receive()


def test_can_factory_passes_explicit_options(monkeypatch):
    bus_factory = Mock()
    monkeypatch.setattr(can, "Bus", bus_factory)
    with make_can_client("virtual", 0, bitrate=250000):
        bus_factory.assert_called_once_with(interface="virtual", channel=0, bitrate=250000, ignore_config=True)
    bus_factory.return_value.shutdown.assert_called_once_with()
