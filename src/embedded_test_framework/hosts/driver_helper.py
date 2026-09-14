"""
Purpose: This class is used to hold drivers for embedded devices (if any) and is installed on the host running the test scripts.
"""
from ..libs.errors import CapabilityError


class DriverHelper:
    """Read-only checks of OS-reported device state; does not install drivers."""
    def __init__(self, host):
        self.host = host

    def device_status(self, identifier):
        for device in self.host.list_peripherals(kind="pnp"):
            if device.identifier.casefold() == identifier.casefold():
                return device.status
        raise CapabilityError("Device is not present in the host PnP inventory")

    def device_ready(self, identifier):
        return self.device_status(identifier).casefold() == "ok"
