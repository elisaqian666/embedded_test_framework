"""Lifecycle and independent capabilities for protocol implementations."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from ..errors import ConfigurationError, TransportError


def positive_timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError("timeout must be a finite positive number")
    return float(value)


@dataclass(frozen=True)
class CommandResult:
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration: float = 0.0

    @property
    def ok(self):
        return self.exit_code == 0

    def check(self):
        if not self.ok:
            raise TransportError(f"Command exited with status {self.exit_code}")
        return self


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        import json
        return json.loads(self.body)


@runtime_checkable
class CommandChannel(Protocol):
    def execute(self, command: str, *, timeout=None) -> CommandResult: ...


@runtime_checkable
class RequestChannel(Protocol):
    def request(self, method: str, path: str, *, payload=None, params=None, headers=None, timeout=None) -> HttpResponse: ...


@runtime_checkable
class ByteChannel(Protocol):
    def exchange(self, data: bytes, *, delimiter: bytes = b"\n", timeout=None) -> bytes: ...


@runtime_checkable
class FileChannel(Protocol):
    def upload(self, local_path, remote_path): ...
    def download(self, remote_path, local_path): ...


class Transport(ABC):
    """One owner per transport. Instances are not generally thread safe."""
    def __init__(self, timeout=5.0):
        self.timeout = positive_timeout(timeout)
        self.connected = False

    def require_connected(self):
        if not self.connected:
            raise TransportError("Transport is not connected")

    def operation_timeout(self, timeout):
        return self.timeout if timeout is None else positive_timeout(timeout)

    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def close(self): ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Transport cleanup failed: {type(cleanup).__name__}")
