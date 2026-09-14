"""Opt-in plugin: pytest_plugins = ['embedded_test_framework.pytest_plugin']."""
from pathlib import Path
import json
import pytest

from .config import Registry, load_device


def pytest_addoption(parser):
    group = parser.getgroup("embedded devices")
    group.addoption("--device-config", default="devices.json", help="Device inventory JSON path")
    group.addoption("--device-name", default="dut", help="Inventory device name")
    group.addoption("--runtime-override", default="{}", help="JSON object merged over runtime configuration")
    group.addoption("--artifact-dir", default=None, help="Evidence directory (default reports/artifacts)")


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
        request.node._embedded_device = device
        yield device


@pytest.fixture
def runtime_overrides():
    """Override with testcase-specific mappings; takes precedence over CLI overrides."""
    return {}


@pytest.fixture
def test_context(request, device_registry, runtime_overrides):
    from .core.context import TestContext
    from .errors import ConfigurationError
    path = Path(request.config.getoption("--device-config"))
    if not path.is_absolute():
        path = request.config.rootpath / path
    try:
        cli = json.loads(request.config.getoption("--runtime-override"))
    except ValueError as exc:
        raise ConfigurationError("--runtime-override must be a JSON object") from exc
    context = TestContext.from_file(path, registry=device_registry, cli=cli, overrides=runtime_overrides)
    artifact_dir = request.config.getoption("--artifact-dir")
    if artifact_dir:
        context.artifact_directory = Path(artifact_dir)
    request.node._embedded_context = context
    with context:
        yield context


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if not report.failed:
        return
    from .testing import DeviceTestBase
    from .diagnostics import EvidenceCollector
    context = getattr(item, "_embedded_context", None)
    device = getattr(item, "_embedded_device", None)
    instance = getattr(item, "instance", None)
    if isinstance(instance, DeviceTestBase):
        context = getattr(instance, "context", context)
        device = getattr(instance, "device", device)
    destination = item.config.getoption("--artifact-dir") or "reports/artifacts"
    try:
        if context is not None:
            artifact = context.collect_evidence(destination if item.config.getoption("--artifact-dir") else None)
        elif device is not None:
            artifact = EvidenceCollector().collect({device.name: device}, destination)
        else:
            return
        report.sections.append(("Embedded evidence", artifact.path))
    except Exception as exc:
        report.sections.append(("Embedded evidence error", getattr(exc, "code", "UNEXPECTED_ERROR")))
