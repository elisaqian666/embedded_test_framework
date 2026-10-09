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
