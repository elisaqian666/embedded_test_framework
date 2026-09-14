import json
from unittest.mock import Mock

import pytest

from embedded_test_framework import ConfigurationUnderTest, Registry, ConfigurationError
from embedded_test_framework.helpers import Helper
from embedded_test_framework.engine import MemoryTransport


def config_file(tmp_path, **extra):
    path = tmp_path / "testconfig.py"
    document = {"devices": {"dut": {"type": "linux", "channels": {
        "shell": {"type": "memory", "responses": {"uname -r": "6.6.1\n"}}
    }}}, "artifacts": str(tmp_path / "artifacts"), **extra}
    path.write_text("TEST_CONFIG = " + repr(document), encoding="utf-8")
    return path


def test_cut_shares_engines_helpers_and_features(tmp_path):
    cut = ConfigurationUnderTest(config_file(tmp_path))
    assert cut.engines.shell is cut.device.engines["shell"]
    assert cut.helpers.host is cut.device.host
    assert cut.features.network is cut.device.capability("network")
    assert not cut.device.connected
    for _ in range(2):
        with cut:
            assert cut.helpers.linux.kernel_version() == "6.6.1"
            assert cut.engines.shell.execute("uname -r").ok
        assert not cut.device.connected and not cut.engines.shell.connected
    with pytest.raises(TypeError):
        cut.engines["other"] = MemoryTransport()
    with pytest.raises(AttributeError):
        cut.engines.unknown


def test_custom_helper_dependency_lifecycle(tmp_path):
    events = []
    class Recorder(Helper):
        def __init__(self, context):
            self.context = context
        def prepare(self):
            assert self.context.devices["dut"].connected
            events.append("prepare")
        def cleanup(self):
            assert self.context.devices["dut"].connected
            events.append("cleanup")
    registry = Registry.defaults()
    registry.register_helper("recorder", Recorder)
    path = config_file(tmp_path, helpers={"recorder": {"type": "recorder", "requires": ["dut"]}})
    with ConfigurationUnderTest(path, registry=registry) as cut:
        assert cut.helpers.recorder is cut.helpers["recorder"]
    cut.close()
    assert events == ["prepare", "cleanup"]


def test_cut_closes_host_resources_before_prepare(tmp_path):
    cut = ConfigurationUnderTest(config_file(tmp_path))
    cut.host.close = Mock()
    cut.close()
    cut.host.close.assert_called_once()


def test_cut_unknown_device_rejected_before_construction(tmp_path):
    with pytest.raises(ConfigurationError):
        ConfigurationUnderTest(config_file(tmp_path), device_name="missing")
