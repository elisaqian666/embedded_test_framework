"""Run an isolated consumer suite to verify fixture setup and teardown."""
import json
from pathlib import Path

pytest_plugins = ["pytester"]


def test_external_plugin_lifecycle(pytester):
    source = (Path(__file__).resolve().parents[1] / "src").as_posix()
    pytester.makeini('[pytest]\npythonpath = "' + source + '"\naddopts = -p no:cacheprovider')
    pytester.makeconftest('''
import pytest
from embedded_test_framework import Registry
from embedded_test_framework.engine import MemoryTransport
pytest_plugins = ["embedded_test_framework.pytest_plugin"]
closed = []
class Tracking(MemoryTransport):
    def close(self):
        closed.append(True)
        super().close()
@pytest.fixture
def device_registry():
    registry = Registry.defaults()
    registry.register_transport("tracking", Tracking)
    return registry
''')
    (pytester.path / "devices.json").write_text(json.dumps({"devices": {"dut": {"channels": {
        "shell": {"type": "tracking", "responses": {"version": "1.0"}}
    }}}}), encoding="utf-8")
    pytester.makepyfile('''
def test_1(dut):
    assert dut.execute("version").stdout == "1.0"
def test_2():
    import conftest
    assert conftest.closed == [True]
''')
    pytester.runpytest_subprocess().assert_outcomes(passed=2)
