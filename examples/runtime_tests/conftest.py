import pytest
from embedded_test_framework import Registry
from product_adapters import register

pytest_plugins = ["embedded_test_framework.pytest_plugin"]


@pytest.fixture
def device_registry():
    registry = Registry.defaults()
    register(registry)
    return registry
