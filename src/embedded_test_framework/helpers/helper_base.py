"""Lifecycle contract for host tools, instruments and product helpers."""
from abc import ABC, abstractmethod


class Helper:
    """Constructors do no I/O. prepare/cleanup may be called for each test."""
    def prepare(self):
        return self

    def cleanup(self):
        pass

    def __enter__(self):
        try:
            return self.prepare()
        except BaseException as exc:
            try:
                self.cleanup()
            except Exception as cleanup:
                exc.add_note(f"Helper cleanup failed: {type(cleanup).__name__}")
            raise

    def __exit__(self, exc_type, exc, tb):
        try:
            self.cleanup()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Helper cleanup failed: {type(cleanup).__name__}")


class PowerSwitcher(Helper, ABC):
    @abstractmethod
    def set_power(self, enabled: bool): ...


class USBSwitcher(Helper, ABC):
    @abstractmethod
    def select_port(self, port: str): ...


class DisplayCapture(Helper, ABC):
    @abstractmethod
    def capture(self, destination): ...
