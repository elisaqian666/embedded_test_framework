"""Configuration-driven runtime; compose layers without exposing driver handles."""
from copy import deepcopy
import json
from pathlib import Path
from types import MappingProxyType

from .lifecycle import ResourceRegistry
from ..errors import ConfigurationError
from ..logging import configure_logging, get_logger, log_operation


def _merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class RuntimeConfig:
    """defaults < file < environment override < CLI override < testcase override.

    Override layers are explicit mappings. ${NAME} substitution runs after merging.
    No arbitrary imports or evaluation are performed.
    """
    def __init__(self, document, *, defaults=None, environment=None, cli=None, overrides=None):
        from ..config import _resolve
        merged = {}
        for layer in (defaults, document, environment, cli, overrides):
            if layer is not None:
                if not isinstance(layer, dict):
                    raise ConfigurationError("Runtime configuration layers must be objects")
                merged = _merge(merged, layer)
        if set(merged) - {"devices", "helpers", "services", "logging", "artifacts", "inputs"}:
            raise ConfigurationError("Unknown runtime configuration fields")
        if not isinstance(merged.get("devices"), dict) or not merged["devices"]:
            raise ConfigurationError("Runtime requires a nonempty devices object")
        for field in ("helpers", "services", "inputs"):
            if not isinstance(merged.get(field, {}), dict):
                raise ConfigurationError(f"{field} must be an object")
        if "artifacts" in merged and (not isinstance(merged["artifacts"], str) or not merged["artifacts"]):
            raise ConfigurationError("artifacts must be a nonempty path string")
        self._document = _resolve(merged)

    @classmethod
    def load(cls, path, **kwargs):
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigurationError("Cannot read runtime configuration JSON") from exc
        return cls(document, **kwargs)

    def as_dict(self):
        return deepcopy(self._document)


class TestContext:
    """Own helpers and devices; prepare helpers first and release devices first."""
    __test__ = False

    def __init__(self, config, *, registry=None):
        from ..config import Registry, DeviceFactory
        from ..lab import Helper
        self.config = config if isinstance(config, RuntimeConfig) else RuntimeConfig(config)
        document = self.config.as_dict()
        if "logging" in document:
            configure_logging(document["logging"])
        self.logger = get_logger("server", type(self).__name__)
        self.registry = registry if registry is not None else Registry.defaults()
        self._resources = ResourceRegistry()
        self.prepared = False
        self.devices, self.helpers, self.services = {}, {}, {}
        self._helper_dependencies = {}
        self.inputs = MappingProxyType(document.get("inputs", {}))
        self.artifact_directory = Path(document.get("artifacts", "reports/artifacts"))
        factory = DeviceFactory(self.registry)
        # Constructors are strictly no-I/O; every created resource is tracked for cleanup.
        constructed = ResourceRegistry()
        try:
            for name, spec in document["devices"].items():
                self.devices[name] = constructed.add(factory.create(name, spec), cleanup="cleanup")
            for name, spec in document.get("helpers", {}).items():
                creator, options = self._factory_options(spec, self.registry.helpers, "helper")
                requires = options.pop("requires", [])
                if (not isinstance(requires, list) or any(not isinstance(key, str) or key not in self.devices for key in requires)
                        or len(set(requires)) != len(requires)):
                    raise ConfigurationError("Helper requires must list unique configured device names")
                self._helper_dependencies[name] = requires
                try:
                    helper = creator(context=self, **options)
                except (TypeError, ValueError) as exc:
                    raise ConfigurationError(f"Invalid helper options for {name!r}") from exc
                if not isinstance(helper, Helper):
                    raise ConfigurationError("Helper factories must return Helper instances")
                self.helpers[name] = constructed.add(helper, cleanup="cleanup")
            for name, spec in document.get("services", {}).items():
                if (not isinstance(spec, dict) or not isinstance(spec.get("device"), str)
                        or spec["device"] not in self.devices):
                    raise ConfigurationError("Service must reference a configured device")
                creator, options = self._factory_options({k: v for k, v in spec.items() if k != "device"},
                                                         self.registry.services, "service")
                try:
                    self.services[name] = creator(self.devices[spec["device"]], **options)
                except (TypeError, ValueError) as exc:
                    raise ConfigurationError(f"Invalid service options for {name!r}") from exc
        except BaseException as exc:
            try:
                constructed.close()
            except Exception as cleanup:
                exc.add_note(f"Construction cleanup failed: {type(cleanup).__name__}")
            raise
        self.devices = MappingProxyType(self.devices)
        self.helpers = MappingProxyType(self.helpers)
        self.services = MappingProxyType(self.services)

    @staticmethod
    def _factory_options(spec, factories, label):
        if not isinstance(spec, dict) or not isinstance(spec.get("type"), str) or spec["type"] not in factories:
            raise ConfigurationError(f"Unknown {label} type")
        return factories[spec["type"]], {k: v for k, v in spec.items() if k != "type"}

    @classmethod
    def from_file(cls, path, *, registry=None, **overrides):
        return cls(RuntimeConfig.load(path, **overrides), registry=registry)

    @property
    def protocols(self):
        """Read-only inventory, not communication handles for bypassing Device."""
        return MappingProxyType({name: device.channel_names for name, device in self.devices.items()})

    @log_operation
    def prepare(self):
        if self.prepared:
            return self
        try:
            self.artifact_directory.mkdir(parents=True, exist_ok=True)
            prepared_devices = set()
            for name, helper in self.helpers.items():
                for device_name in self._helper_dependencies[name]:
                    if device_name not in prepared_devices:
                        device = self.devices[device_name]
                        self._resources.add(device, cleanup="cleanup")
                        device.prepare()
                        prepared_devices.add(device_name)
                self._resources.add(helper, cleanup="cleanup")
                helper.prepare()
            for name, device in self.devices.items():
                if name in prepared_devices:
                    continue
                self._resources.add(device, cleanup="cleanup")
                device.prepare()
            self.prepared = True
            return self
        except BaseException as exc:
            self._resources.__exit__(type(exc), exc, exc.__traceback__)
            raise

    @log_operation
    def close(self):
        try:
            self._resources.close()
        finally:
            self.prepared = False

    def collect_evidence(self, destination=None):
        from ..diagnostics import EvidenceCollector
        return EvidenceCollector().collect(self.devices, destination or self.artifact_directory)

    def __enter__(self):
        return self.prepare()

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            try:
                self.collect_evidence()
            except Exception as diagnostic:
                exc.add_note(f"Evidence collection failed: {type(diagnostic).__name__}")
        try:
            self.close()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Runtime cleanup failed: {type(cleanup).__name__}")
