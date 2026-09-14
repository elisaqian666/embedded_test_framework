import json
from pathlib import Path
import pytest

pytest_plugins = ["pytester"]


def test_lifecycle_in_pytest(pytester):
    source = (Path(__file__).resolve().parents[1] / "src").as_posix()
    pytester.makeini(f'[pytest]\npythonpath = "{source}"\naddopts = -p no:cacheprovider')
    (pytester.path / "devices.json").write_text(json.dumps({"devices": {"dut": {
        "channels": {"shell": {"type": "memory", "responses": {"version": "1.0"}}}
    }}}), encoding="utf-8")
    pytester.makepyfile('''
from pathlib import Path
from embedded_test_framework.dut import DeviceTestBase
events = []
class TestBoard(DeviceTestBase):
    config_path = Path(__file__).with_name("devices.json")
    @classmethod
    def setupclass(cls):
        assert not cls.device.connected
        assert cls.cut.device is cls.device
        assert cls.cut.engines.shell is cls.device.engines["shell"]
        events.append("class setup")
    def setup(self):
        assert self.device.connected
        events.append("setup")
    def teardown(self):
        assert self.device.connected
        events.append("teardown")
    @classmethod
    def teardownclass(cls):
        assert not cls.device.connected
        events.append("class teardown")
    def test_first(self):
        assert self.device.execute("version").stdout == "1.0"
        assert self.cut.engines.shell.execute("version").stdout == "1.0"
    def test_second(self):
        assert self.device.connected
def test_order():
    assert events == ["class setup", "setup", "teardown", "setup", "teardown", "class teardown"]
''')
    pytester.runpytest_subprocess().assert_outcomes(passed=3)


@pytest.mark.parametrize("hook", ["setupclass", "setup", "teardown", "teardownclass"])
def test_hook_failure_releases_device(tmp_path, hook):
    from embedded_test_framework.dut import DeviceTestBase
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"devices": {"dut": {"channels": {"shell": {"type": "memory"}}}}}), encoding="utf-8")
    class Board(DeviceTestBase):
        config_path = path
    def fail(self):
        raise RuntimeError("hook failed")
    setattr(Board, hook, classmethod(fail) if hook in ("setupclass", "teardownclass") else fail)
    if hook == "setupclass":
        with pytest.raises(RuntimeError):
            Board.setup_class()
        assert not Board.device.connected
        return
    Board.setup_class()
    device = Board.device
    instance = Board()
    try:
        if hook == "setup":
            with pytest.raises(RuntimeError):
                instance.setup_method(fail)
        else:
            instance.setup_method(fail)
            if hook == "teardown":
                with pytest.raises(RuntimeError):
                    instance.teardown_method(fail)
            else:
                with pytest.raises(RuntimeError):
                    Board.teardown_class()
        assert not device.connected
    finally:
        device.close()
