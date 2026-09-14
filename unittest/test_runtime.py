import json
from unittest.mock import Mock

import pytest

from embedded_test_framework import (TestContext, RuntimeConfig, ResourceRegistry, Registry, Device,
                                     ConfigurationError, CleanupError, TransportError)
from embedded_test_framework.helpers import Helper


def inventory():
    return {"devices": {"dut": {"type": "linux", "channels": {"shell": {
        "type": "memory", "responses": {"ifconfig eth0": "inet 10.0.0.2\n"}
    }}}}, "services": {"network": {"type": "network", "device": "dut"}}}


def test_context_config_service_and_reuse(tmp_path):
    document = inventory()
    document["artifacts"] = str(tmp_path)
    context = TestContext(document)
    assert not context.devices["dut"].connected
    assert context.protocols == {"dut": ("shell",)}
    for _ in range(2):
        with context:
            assert context.services["network"].get_ipv4_addresses() == ["10.0.0.2"]
            assert context.prepare() is context
        assert not context.devices["dut"].connected


def test_overrides_merge_then_resolve(monkeypatch):
    monkeypatch.setenv("TEST_BOARD", "board-1")
    original = {"devices": {"dut": {"channels": {"shell": {"type": "memory"}}}},
                "inputs": {"host": "${TEST_BOARD}", "mode": "file"}}
    config = RuntimeConfig(original, defaults={"inputs": {"mode": "default", "firmware": "a.bin"}},
                           environment={"inputs": {"mode": "env"}}, cli={"inputs": {"mode": "cli"}},
                           overrides={"inputs": {"mode": "test"}})
    assert config.as_dict()["inputs"] == {"host": "board-1", "mode": "test", "firmware": "a.bin"}
    assert original["inputs"]["mode"] == "file"
    copy = config.as_dict()
    copy["inputs"]["mode"] = "changed"
    assert config.as_dict()["inputs"]["mode"] == "test"


@pytest.mark.parametrize("document", [{}, {"devices": []}, {"devices": {"dut": {}}, "helpers": []},
                                       {"devices": {"dut": {}}, "unexpected": True}])
def test_invalid_runtime_configuration(document):
    with pytest.raises(ConfigurationError):
        RuntimeConfig(document)


def test_prepare_rollback_includes_partially_prepared_resource(tmp_path):
    events = []
    class Board(Device):
        def prepare(self):
            events.append(self.name + "+")
            super().prepare()
            if self.name == "bad":
                raise TransportError("offline")
        def cleanup(self):
            events.append(self.name + "-")
            super().cleanup()
    class Lab(Helper):
        def __init__(self, context):
            self.context = context
        def prepare(self):
            events.append("lab+")
        def cleanup(self):
            events.append("lab-")
    registry = Registry.defaults()
    registry.register_device("board", Board)
    registry.register_helper("lab", Lab)
    spec = {"type": "board", "channels": {"shell": {"type": "memory"}}}
    context = TestContext({"devices": {"good": spec, "bad": spec}, "helpers": {"lab": {"type": "lab"}},
                           "artifacts": str(tmp_path)}, registry=registry)
    with pytest.raises(TransportError):
        context.prepare()
    assert events == ["lab+", "good+", "bad+", "bad-", "good-", "lab-"]
    assert not context.prepared
    assert all(not d.connected for d in context.devices.values())
    context.close()
    assert len(events) == 6


def test_resources_preserve_original_and_attempt_every_cleanup():
    first, second = Mock(), Mock()
    second.close.side_effect = RuntimeError("cannot close")
    original = ValueError("test failure")
    with pytest.raises(ValueError) as caught:
        with ResourceRegistry() as resources:
            resources.add(first)
            resources.add(second)
            raise original
    assert caught.value is original
    assert original.__notes__
    first.close.assert_called_once()
    second.close.assert_called_once()
    resources.close()


def test_duplicate_resource_rejected():
    resources = ResourceRegistry()
    item = Mock()
    resources.add(item)
    with pytest.raises(ConfigurationError):
        resources.add(item)
    resources.close()


def test_helper_dependencies_stay_connected_until_helper_is_restored(tmp_path):
    events = []
    class Instrument(Device):
        def prepare(self):
            events.append("instrument+")
            return super().prepare()
        def cleanup(self):
            events.append("instrument-")
            super().cleanup()
    class Lab(Helper):
        def __init__(self, context):
            self.instrument = context.devices["instrument"]
        def prepare(self):
            assert self.instrument.connected
            events.append("helper+")
        def cleanup(self):
            assert self.instrument.connected
            events.append("helper-")
    registry = Registry.defaults()
    registry.register_device("instrument", Instrument)
    registry.register_helper("dependent", Lab)
    with TestContext({"devices": {"instrument": {"type": "instrument", "channels": {"shell": {"type": "memory"}}}},
                      "helpers": {"lab": {"type": "dependent", "requires": ["instrument"]}},
                      "artifacts": str(tmp_path)}, registry=registry):
        assert events == ["instrument+", "helper+"]
    assert events == ["instrument+", "helper+", "helper-", "instrument-"]


def test_explicit_plugin_loading(monkeypatch):
    entry = Mock(name="entry")
    entry.name = "lab-plugin"
    entry.load.return_value = lambda registry: registry.register_device("custom", Device)
    monkeypatch.setattr("importlib.metadata.entry_points", lambda **kwargs: [entry])
    registry = Registry.defaults()
    assert "custom" not in registry.devices
    registry.load_plugins(["lab-plugin"])
    assert registry.devices["custom"] is Device
    with pytest.raises(ConfigurationError):
        registry.load_plugins(["unknown"])


def test_context_exception_writes_evidence_before_cleanup(tmp_path):
    context = TestContext({**inventory(), "artifacts": str(tmp_path)})
    with pytest.raises(ValueError):
        with context:
            raise ValueError("test failure")
    manifests = list(tmp_path.glob("*/manifest.json"))
    assert len(manifests) == 1
    assert all(item["status"] == "unsupported" for item in json.loads(manifests[0].read_text()))
    assert not context.devices["dut"].connected
