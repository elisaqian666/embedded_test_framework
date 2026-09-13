"""Opt-in plugin: pytest_plugins = ['embedded_test_framework.pytest_plugin']."""
from pathlib import Path
import pytest

from .config import Registry, load_device


def pytest_addoption(parser):
    group = parser.getgroup("embedded devices")
    group.addoption("--device-config", default="devices.json", help="Device inventory JSON path")
    group.addoption("--device-name", default="dut", help="Inventory device name")


@pytest.fixture
def device_registry():
    """Override this fixture to register product transports and devices."""
    return Registry.defaults()


@pytest.fixture
def dut(request, device_registry):
    """Function-scoped device: failed setup rolls back; teardown closes all channels."""
    path = Path(request.config.getoption("--device-config"))
    if not path.is_absolute():
        path = request.config.rootpath / path
    with load_device(path, request.config.getoption("--device-name"), registry=device_registry) as device:
        yield device
