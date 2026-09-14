import json
import pytest
from embedded_test_framework import DeviceFactory, Registry, Device, load_device, ConfigurationError
from embedded_test_framework.engine import MemoryTransport


@pytest.mark.parametrize("spec", [{}, {"channels": {}}, {"channels": {"x": {"type": "unknown"}}},
    {"channels": {"x": {"type": "memory", "typo": 1}}},
    {"channels": {"x": {"type": "memory"}}, "metadata": []},
    {"channels": {"x": {"type": "memory"}}, "type": "unknown"}])
def test_invalid_device_configuration(spec):
    with pytest.raises(ConfigurationError):
        DeviceFactory().create("dut", spec)


def test_custom_device_and_bad_factory():
    class Board(Device):
        pass
    registry = Registry.defaults()
    registry.register_device("board", Board)
    spec = {"type": "board", "channels": {"shell": {"type": "memory"}}}
    board = DeviceFactory(registry).create("dut", spec)
    assert isinstance(board, Board) and not board.connected
    registry.register_transport("bad", lambda: object())
    with pytest.raises(ConfigurationError):
        DeviceFactory(registry).create("dut", {"channels": {"shell": {"type": "bad"}}})


@pytest.mark.parametrize("document", ["not json", "[]", '{}', '{"devices": []}', '{"devices": {}}'])
def test_inventory_errors(tmp_path, document):
    path = tmp_path / "devices.json"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_device(path)
