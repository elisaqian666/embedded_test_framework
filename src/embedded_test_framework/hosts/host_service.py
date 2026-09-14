from ..libs.logging import get_logger, log_operation
"""Host-side board discovery, usable before a device transport is opened."""
import time

from ..libs.errors import ConfigurationError, OperationTimeout
from ..libs.validation import positive_timeout


class HostService:
    def __init__(self, host):
        self.logger = get_logger("server", type(self).__name__)
        self.host = host

    @log_operation
    def find_peripherals(self, *, kind="serial", identifier=None, vid=None, pid=None,
                         serial_number=None, healthy_only=False):
        if all(value is None for value in (identifier, vid, pid, serial_number)):
            raise ConfigurationError("Specify at least one peripheral identity criterion")
        return [p for p in self.host.list_peripherals(kind=kind)
                if (identifier is None or p.identifier.casefold() == identifier.casefold())
                and (vid is None or p.vid == vid) and (pid is None or p.pid == pid)
                and (serial_number is None or p.serial_number == serial_number)
                and (not healthy_only or p.status.casefold() in ("ok", "present"))]

    @log_operation
    def wait_for_peripheral(self, *, timeout=10.0, interval=0.2, **criteria):
        deadline = time.monotonic() + positive_timeout(timeout)
        positive_timeout(interval)
        while True:
            matches = self.find_peripherals(**criteria)
            if matches:
                return matches[0]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OperationTimeout("Peripheral was not detected on host")
            time.sleep(min(interval, remaining))
