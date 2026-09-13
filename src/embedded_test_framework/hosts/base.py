"""Host-side contracts, independent of device communication protocols."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Peripheral:
    identifier: str
    name: str
    kind: str
    status: str = "unknown"
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str


class Host(ABC):
    """Host owns only applications it starts. close() must be repeatable."""
    @abstractmethod
    def run(self, args, *, timeout=None, cwd=None): ...

    @abstractmethod
    def start_application(self, args, *, cwd=None, visible=False): ...

    @abstractmethod
    def list_processes(self): ...

    @abstractmethod
    def list_peripherals(self, *, kind="serial"): ...

    @abstractmethod
    def close(self): ...

    def is_process_running(self, name):
        return any(process.name.casefold() == name.casefold() for process in self.list_processes())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Host cleanup failed: {type(cleanup).__name__}")
