from ..logging import get_logger, log_operation
"""Device composition independent of pytest/unittest and product assertions."""

from types import MappingProxyType
from ..errors import CapabilityError, CleanupError, ConfigurationError, TransportError, DeviceDisconnected
from ..core.contracts import CommandChannel, RequestChannel, ByteChannel, FileChannel


class Device:
    def __init__(self, name, channels, *, metadata=None, host=None):
        if not isinstance(name, str) or not name or not channels:
            raise ConfigurationError("A device requires a name and at least one channel")
        if len({id(t) for t in channels.values()}) != len(channels):
            raise ConfigurationError("Each channel must own a distinct transport")
        self.name = name
        from ..hosts import LocalHost
        self.host = host if host is not None else LocalHost()
        self._owns_host = host is None
        self._channels = dict(channels)
        self._capabilities = {}
        self.metadata = dict(metadata or {})
        self.connected = False
        self.logger = get_logger("dut", name)

    @log_operation
    def connect(self):
        if self.connected:
            return self
        opened = []
        try:
            for transport in self._channels.values():
                opened.append(transport)
                transport.connect()
        except Exception as exc:
            for transport in reversed(opened):
                try:
                    transport.close()
                except Exception as cleanup:
                    exc.add_note(f"Rollback failed: {type(cleanup).__name__}")
            if self._owns_host:
                try:
                    self.host.close()
                except Exception as cleanup:
                    exc.add_note(f"Host rollback failed: {type(cleanup).__name__}")
            raise
        self.connected = True
        return self

    @log_operation
    def close(self):
        errors = []
        for transport in reversed(list(self._channels.values())):
            try:
                transport.close()
            except Exception as exc:
                errors.append(exc)
        if self._owns_host:
            try:
                self.host.close()
            except Exception as exc:
                errors.append(exc)
        self.connected = False
        if errors:
            raise CleanupError(errors)

    def channel(self, name, capability=None):
        if not self.connected:
            raise DeviceDisconnected("Device is not connected")
        if name not in self._channels:
            raise CapabilityError(f"Device {self.name!r} has no channel {name!r}")
        transport = self._channels[name]
        if capability is not None and not isinstance(transport, capability):
            raise CapabilityError(f"Channel {name!r} does not implement {capability.__name__}")
        return transport

    @property
    def capabilities(self):
        return MappingProxyType(self._capabilities)

    @property
    def channel_names(self):
        return tuple(self._channels)

    def bind_capability(self, name, capability, *, replace=False):
        from ..capabilities import Capability
        if not isinstance(name, str) or not name or (name in self._capabilities and not replace):
            raise ConfigurationError("Capability requires a unique nonempty name")
        if not isinstance(capability, Capability) or capability.device is not self:
            raise ConfigurationError("Capability must belong to this device")
        self._capabilities[name] = capability
        return capability

    def capability(self, name, contract=None):
        if name not in self._capabilities:
            raise CapabilityError(f"Device {self.name!r} has no capability {name!r}")
        capability = self._capabilities[name]
        if contract is not None and not isinstance(capability, contract):
            raise CapabilityError(f"Capability {name!r} does not implement the requested contract")
        return capability

    def prepare(self):
        return self.connect()

    def cleanup(self):
        return self.close()

    @log_operation
    def reconnect(self):
        """Explicit recovery; commands are never replayed automatically."""
        self.close()
        return self.connect()

    def reboot(self):
        return self.capability("power").reboot()

    def flash(self, image):
        return self.capability("update").flash(image)

    def collect_logs(self, destination):
        return self.capability("logging").collect_logs(destination)

    def health_check(self):
        return self.capability("health").health_check()

    def detect_crash(self):
        return self.capability("crash").detect_crash()

    def get_ipv4_addresses(self, interface="eth0", *, channel="shell", command="ifconfig",
                           include_loopback=False, timeout=None):
        """Legacy shell query. New portable clients use the network capability."""
        from ..adapters.linux import LinuxNetworkCapability
        return LinuxNetworkCapability(self, channel=channel).get_ipv4_addresses(
            interface, command=command, include_loopback=include_loopback, timeout=timeout)

    def execute(self, command, *, channel="shell", timeout=None):
        return self.channel(channel, CommandChannel).execute(command, timeout=timeout)

    def request(self, method, path, *, channel="api", **kwargs):
        return self.channel(channel, RequestChannel).request(method, path, **kwargs)

    def exchange(self, data, *, channel="console", **kwargs):
        return self.channel(channel, ByteChannel).exchange(data, **kwargs)

    def download(self, remote_path, local_path, *, channel="files"):
        return self.channel(channel, FileChannel).download(remote_path, local_path)

    def upload(self, local_path, remote_path, *, channel="files"):
        return self.channel(channel, FileChannel).upload(local_path, remote_path)

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Device cleanup failed: {type(cleanup).__name__}")
