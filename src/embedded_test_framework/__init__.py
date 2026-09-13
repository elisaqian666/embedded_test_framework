"""Public embedded device testing SDK."""
from .config import DeviceFactory, Registry, load_device
from .devices import Device
from .hosts import Host, LocalHost, Peripheral, ProcessInfo, Application
from .errors import FrameworkError, ConfigurationError, TransportError, OperationTimeout, CapabilityError, CleanupError
from .engine import CommandResult, HttpResponse

__version__ = "0.2.0"
__all__ = ["Device", "DeviceFactory", "Registry", "load_device", "CommandResult", "HttpResponse",
           "FrameworkError", "ConfigurationError", "TransportError", "OperationTimeout", "CapabilityError", "CleanupError",
           "Host", "LocalHost", "Peripheral", "ProcessInfo", "Application"]
