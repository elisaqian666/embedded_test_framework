from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from embedded_test_framework.embedded_test_base import EmbeddedTestCase


def test_inherited_crash_check_fails_when_coredumps_were_collected(tmp_path: Path, monkeypatch) -> None:
    class SampleCase(EmbeddedTestCase):
        pass

    sample = SampleCase()
    sample.test_method_log_store_folder = str(tmp_path)
    assert hasattr(SampleCase, "test_zzzz_check_for_crashes")
    monkeypatch.setattr(SampleCase, "_collect_linux_coredumps", classmethod(lambda cls, destination: [destination / "core.app"]))

    with pytest.raises(AssertionError, match="core.app"):
        sample.test_zzzz_check_for_crashes()


@pytest.mark.parametrize("failure", [None, "connect", "capability", "engine"])
def test_runtime_cleanup_is_registered_before_initialization(failure, tmp_path, monkeypatch):
    from embedded_test_framework.basic_test_setup import BasicTestClass
    from embedded_test_framework.devices import Capability
    from embedded_test_framework.runtime import Runtime

    class SampleCase(EmbeddedTestCase):
        dut_name = "board"
        required_capabilities = (Capability.SHELL,)
        config = {"devices": {"board": {}}}
        config_file = "config.py"
        base_log_store_folder = str(tmp_path)

    dut = Mock(name="board")
    dut.supports.return_value = failure != "capability"
    runtime = Mock(duts={"board": dut})
    if failure == "connect":
        runtime.connect.side_effect = RuntimeError("connect failed")
    if failure == "engine":
        dut.engine.side_effect = RuntimeError("engine failed")
    finalizers = []
    SampleCase.pytest_request = SimpleNamespace(node=SimpleNamespace(nodeid="sample"), addfinalizer=finalizers.append)
    monkeypatch.setattr(BasicTestClass, "setUpClass", classmethod(lambda cls: None))
    monkeypatch.setattr(Runtime, "from_mapping", lambda *args, **kwargs: runtime)
    if failure:
        with pytest.raises(RuntimeError):
            SampleCase.setUpClass()
    else:
        SampleCase.setUpClass()
        SampleCase.tearDownClass()
    assert finalizers == [runtime.close]
    runtime.close.assert_not_called()
    finalizers.pop()()
    runtime.close.assert_called_once_with()


@pytest.mark.parametrize("failure", ["download", "scan", "metadata"])
def test_crash_check_never_passes_when_collection_fails(failure, tmp_path):
    from embedded_test_framework.configurator.configurator_dut import ConnectionConfig, DeviceConfig, EngineFactory
    from embedded_test_framework.devices.linux import LinuxDevice
    from embedded_test_framework.lib.command_result import CommandResult

    engine = Mock()
    engine.exec_command.return_value = CommandResult("/var/crash/core.app\n")
    if failure == "download":
        engine.get_files.side_effect = OSError("download failed")
    elif failure == "scan":
        engine.exec_command.return_value = CommandResult("", 1, "Permission denied")
    metadata = {"coredump_paths": ["/var/crash"] if failure != "metadata" else "invalid"}
    config = DeviceConfig("board", {"ssh": ConnectionConfig("ssh")}, "ssh", metadata)

    class SampleCase(EmbeddedTestCase):
        pass

    with LinuxDevice(config, EngineFactory({"ssh": lambda: engine})) as device:
        SampleCase.duts = {"board": device}
        sample = SampleCase()
        sample.test_method_log_store_folder = str(tmp_path)
        expected = AssertionError if failure == "download" else ExceptionGroup
        with pytest.raises(expected):
            sample.test_zzzz_check_for_crashes()


def test_scan_failure_does_not_prevent_checking_remaining_devices(tmp_path):
    from embedded_test_framework.configurator.configurator_dut import ConnectionConfig, DeviceConfig, EngineFactory
    from embedded_test_framework.devices.linux import LinuxDevice
    from embedded_test_framework.lib.command_result import CommandResult

    class SampleCase(EmbeddedTestCase):
        pass

    engines = [Mock(), Mock()]
    engines[0].exec_command.side_effect = OSError("device disconnected")
    engines[1].exec_command.return_value = CommandResult()
    devices = []
    for index, engine in enumerate(engines):
        config = DeviceConfig(str(index), {"ssh": ConnectionConfig("ssh")}, "ssh")
        device = LinuxDevice(config, EngineFactory())
        device._connected = True
        device._engines["ssh"] = engine
        devices.append(device)
    SampleCase.duts = {device.name: device for device in devices}
    with pytest.raises(ExceptionGroup) as caught:
        SampleCase._collect_linux_coredumps(tmp_path)
    assert len(caught.value.exceptions) == 1
    assert "DUT 0" in caught.value.exceptions[0].__notes__[0]
    for engine in engines:
        engine.exec_command.assert_called_once()
