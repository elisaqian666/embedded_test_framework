"""Stable communication capability contracts and result values."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from ..errors import CommandFailed


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
            raise CommandFailed(self)
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


