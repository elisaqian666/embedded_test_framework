"""External laboratory resource contracts; vendor implementations are plugins."""
from abc import ABC, abstractmethod
from ..hosts import LocalHost as HostController


class Helper(ABC):
    """Construct without I/O; prepare acquires resources and cleanup releases them."""
    def prepare(self):
        return self

    @abstractmethod
    def cleanup(self): ...

    def close(self):
        return self.cleanup()


class PowerSwitcher(Helper):
    @abstractmethod
    def set_power(self, outlet, enabled): ...


class UsbSwitcher(Helper):
    @abstractmethod
    def select(self, port): ...


class DisplayEmulator(Helper):
    @abstractmethod
    def configure(self, profile): ...


class CaptureDevice(Helper):
    @abstractmethod
    def capture(self, destination): ...


class Analyzer(Helper):
    @abstractmethod
    def measure(self): ...


class Sniffer(Helper):
    @abstractmethod
    def start(self, destination): ...

    @abstractmethod
    def stop(self): ...


class BuildProvider(Helper):
    @abstractmethod
    def fetch(self, reference, destination): ...
