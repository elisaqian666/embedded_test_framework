"""ConfigurationUnderTest (cut): the composition root used by test classes."""
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from ..configurators.runtime import RuntimeConfig, TestContext
from ..libs.resource_registry import ResourceRegistry
from ..helpers.he_linux_commands import LinuxCommandHelper
from ..helpers import ArtifactHelper, BuildHelper, ValgrindHelper
from ..libs.errors import ConfigurationError


class Resources(Mapping):
    """Read-only named resources: collection['name'] or collection.name."""
    def __init__(self, resources):
        self._resources = MappingProxyType(dict(resources))

    def __getitem__(self, name):
        return self._resources[name]

    def __iter__(self):
        return iter(self._resources)

    def __len__(self):
        return len(self._resources)

    def __getattr__(self, name):
        try:
            return self._resources[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class ConfigurationUnderTest(TestContext):
    """Build once, prepare and close per test. No hardware I/O during construction.

    Helpers, engines and features belong to their existing lifecycle owners;
    exposing a resource through cut never creates a second connection.
    """
    def __init__(self, config_file, *, registry=None, device_name=None, **overrides):
        self.config_file = Path(config_file).resolve()
        config = RuntimeConfig.load(self.config_file, **overrides)
        names = config.as_dict()["devices"]
        if device_name is None:
            device_name = "dut" if "dut" in names else next(iter(names))
        if device_name not in names:
            raise ConfigurationError("device_name must identify a configured device")
        super().__init__(config, registry=registry)
        self.device = self.devices[device_name]
        self.dut = self.device
        self.engines = Resources(self.device.engines)
        self.host = self.device.host
        self._configured_helpers = self.helpers
        # Borrowed convenience views; the device owns the host lifecycle.
        self._helper_views = {"host": self.host, "linux": LinuxCommandHelper(self.device),
                              "artifacts": ArtifactHelper(), "build": BuildHelper(self.host),
                              "valgrind": ValgrindHelper(self.device), **self.helpers}

    @property
    def features(self):
        return Resources(self.device.capabilities)

    @classmethod
    def from_file(cls, path, *, registry=None, **overrides):
        return cls(path, registry=registry, **overrides)

    @property
    def helpers(self):
        return Resources(self._helper_views) if hasattr(self, "_helper_views") else self._configured_helpers

    @helpers.setter
    def helpers(self, value):
        self._configured_helpers = value

    def _helpers_to_prepare(self):
        return self._configured_helpers

    def close(self):
        was_prepared = self.prepared
        super().close()
        if not was_prepared:
            # Class hooks can use host resources before per-test preparation begins.
            resources = ResourceRegistry()
            for device in self.devices.values():
                resources.add(device, cleanup="cleanup")
            resources.close()

    def create_device(self, name=None):
        """Return an already constructed device; callers should prefer cut's lifecycle."""
        if name is None:
            return self.device
        try:
            return self.devices[name]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown configured device {name!r}") from exc
