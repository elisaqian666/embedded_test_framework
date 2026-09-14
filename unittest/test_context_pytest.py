import json
from pathlib import Path

pytest_plugins = ["pytester"]


def test_failed_test_collects_evidence_while_connected_and_cleans_up(pytester):
    source = (Path(__file__).resolve().parents[1] / "src").as_posix()
    pytester.makeini(f'[pytest]\npythonpath = "{source}"\naddopts = -p no:cacheprovider')
    pytester.makeconftest('''
import pytest
from pathlib import Path
from embedded_test_framework import Registry
from embedded_test_framework.capabilities import LoggingCapability
pytest_plugins = ["embedded_test_framework.pytest_plugin"]
class Logs(LoggingCapability):
    def collect_logs(self, destination):
        assert self.device.connected
        Path(destination, "device.log").write_text("captured before cleanup")
@pytest.fixture
def device_registry():
    registry = Registry.defaults()
    registry.register_capability("logs", Logs)
    return registry
''')
    (pytester.path / "devices.json").write_text(json.dumps({"devices": {"dut": {
        "channels": {"shell": {"type": "memory"}}, "capabilities": {"logging": {"type": "logs"}}
    }}}))
    pytester.makepyfile('''
saved = []
def test_failure(test_context):
    saved.append(test_context)
    assert False, "deliberate failure"
def test_cleanup():
    assert not saved[0].devices["dut"].connected
''')
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, failed=1)
    logs = list(pytester.path.glob("reports/artifacts/*/device-0/device.log"))
    assert logs and logs[0].read_text() == "captured before cleanup"


def test_embedded_test_case_multi_device_lifecycle(pytester):
    source = (Path(__file__).resolve().parents[1] / "src").as_posix()
    pytester.makeini(f'[pytest]\npythonpath = "{source}"\naddopts = -p no:cacheprovider')
    spec = {"channels": {"shell": {"type": "memory"}}}
    (pytester.path / "devices.json").write_text(json.dumps({"devices": {"dut": spec, "peer": spec}}))
    pytester.makepyfile('''
from pathlib import Path
from embedded_test_framework.testing import EmbeddedTestCase
saved = []
class TestBoard(EmbeddedTestCase):
    config_path = Path(__file__).with_name("devices.json")
    @classmethod
    def setupclass(cls):
        assert not cls.context.prepared
        saved.append(cls.context)
    def test_first(self):
        assert all(device.connected for device in self.context.devices.values())
    def test_second(self):
        assert self.context.prepared
def test_cleanup():
    assert all(not device.connected for device in saved[0].devices.values())
''')
    pytester.runpytest_subprocess().assert_outcomes(passed=3)
