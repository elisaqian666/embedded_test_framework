"""Device capabilities. Implement adapters against Device APIs, never raw handles."""
from abc import ABC, abstractmethod


class Capability:
    def __init__(self, device):
        self.device = device


class NetworkCapability(Capability, ABC):
    @abstractmethod
    def get_ipv4_addresses(self, interface="eth0", *, timeout=None): ...


class LoggingCapability(Capability, ABC):
    @abstractmethod
    def collect_logs(self, destination): ...


class UpdateCapability(Capability, ABC):
    @abstractmethod
    def flash(self, image): ...


class PowerCapability(Capability, ABC):
    @abstractmethod
    def reboot(self): ...


class HealthCapability(Capability, ABC):
    @abstractmethod
    def health_check(self): ...


class CrashCapability(Capability, ABC):
    @abstractmethod
    def detect_crash(self): ...


class PerformanceCapability(Capability, ABC):
    @abstractmethod
    def sample(self): ...
