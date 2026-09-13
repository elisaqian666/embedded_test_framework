"""Explicit registries and JSON inventory. Construction never connects hardware."""
import json
import os
from pathlib import Path
import re

from .devices import Device
from .hosts import Host, LocalHost
from .errors import ConfigurationError
from .engine import HttpTransport, SSHTransport, ADBTransport, SerialTransport, FTPTransport, MemoryTransport, Transport


class Registry:
    def __init__(self):
        self.transports = {}
        self.devices = {}
        self.hosts = {}

    def register_host(self, name, factory):
        self._register(self.hosts, name, factory)

    def register_transport(self, name, factory):
        self._register(self.transports, name, factory)

    def register_device(self, name, factory):
        self._register(self.devices, name, factory)

    @staticmethod
    def _register(target, name, factory):
        if not isinstance(name, str) or not name or not callable(factory) or name in target:
            raise ConfigurationError("Registration requires a unique name and callable factory")
        target[name] = factory

    @classmethod
    def defaults(cls):
        registry = cls()
        for name, factory in {"http": HttpTransport, "ssh": SSHTransport, "adb": ADBTransport,
                              "serial": SerialTransport, "ftp": FTPTransport, "memory": MemoryTransport}.items():
            registry.register_transport(name, factory)
        registry.register_device("generic", Device)
        registry.register_host("local", LocalHost)
        return registry


def _resolve(value):
    if isinstance(value, str):
        def substitute(match):
            name = match.group(1)
            if name not in os.environ:
                raise ConfigurationError(f"Required environment variable {name} is missing")
            return os.environ[name]
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", substitute, value)
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    return value


class DeviceFactory:
    def __init__(self, registry=None):
        self.registry = registry if registry is not None else Registry.defaults()

    def create(self, name, spec):
        if not isinstance(spec, dict) or set(spec) - {"type", "channels", "metadata", "host"}:
            raise ConfigurationError("Invalid device specification fields")
        specs = spec.get("channels")
        if not isinstance(specs, dict) or not specs:
            raise ConfigurationError("channels must be a nonempty object")
        metadata = spec.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ConfigurationError("metadata must be an object")
        kind = spec.get("type", "generic")
        if not isinstance(kind, str) or kind not in self.registry.devices:
            raise ConfigurationError("Unknown device type")
        channels = {}
        for channel, options in specs.items():
            if not isinstance(channel, str) or not channel or not isinstance(options, dict):
                raise ConfigurationError("Invalid channel specification")
            protocol = options.get("type")
            if not isinstance(protocol, str) or protocol not in self.registry.transports:
                raise ConfigurationError(f"Unknown transport on channel {channel!r}")
            kwargs = _resolve({k: v for k, v in options.items() if k != "type"})
            try:
                transport = self.registry.transports[protocol](**kwargs)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"Invalid options for channel {channel!r}") from exc
            if not isinstance(transport, Transport):
                raise ConfigurationError("Transport factories must return Transport instances")
            channels[channel] = transport
        host_spec = spec.get("host")
        if host_spec is None:
            return self.registry.devices[kind](name, channels, metadata=_resolve(metadata))
        if not isinstance(host_spec, dict):
            raise ConfigurationError("host must be an object")
        host_type = host_spec.get("type", "local")
        if not isinstance(host_type, str) or host_type not in self.registry.hosts:
            raise ConfigurationError("Unknown host type")
        try:
            host = self.registry.hosts[host_type](**_resolve({k: v for k, v in host_spec.items() if k != "type"}))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("Invalid host options") from exc
        if not isinstance(host, Host):
            raise ConfigurationError("Host factories must return Host instances")
        device = self.registry.devices[kind](name, channels, metadata=_resolve(metadata), host=host)
        device._owns_host = True
        return device


def load_device(path, name="dut", *, registry=None):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError("Cannot read device inventory JSON") from exc
    if not isinstance(document, dict) or set(document) != {"devices"} or not isinstance(document["devices"], dict):
        raise ConfigurationError("Inventory must contain a devices object")
    if name not in document["devices"]:
        raise ConfigurationError(f"Device {name!r} not found in inventory")
    return DeviceFactory(registry).create(name, document["devices"][name])
