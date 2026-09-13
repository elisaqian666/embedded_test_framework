from ..logging import get_logger, log_operation
"""Device composition independent of pytest/unittest and product assertions."""

from ..errors import CapabilityError, CleanupError, ConfigurationError, TransportError
from ..engine import CommandChannel, RequestChannel, ByteChannel, FileChannel


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
            raise TransportError("Device is not connected")
        if name not in self._channels:
            raise CapabilityError(f"Device {self.name!r} has no channel {name!r}")
        transport = self._channels[name]
        if capability is not None and not isinstance(transport, capability):
            raise CapabilityError(f"Channel {name!r} does not implement {capability.__name__}")
        return transport

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
