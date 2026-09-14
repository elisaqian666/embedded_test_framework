from ..libs.logging import log_operation
import threading
import time

from .transport_base import Transport
from ..libs.errors import ConfigurationError, OperationTimeout, TransportError


class SerialTransport(Transport):
    """Atomic request/reply byte exchange with a total write/read deadline."""
    def __init__(self, port, *, baudrate=115200, timeout=5.0):
        super().__init__(timeout)
        self.port, self.baudrate = port, baudrate
        self._serial = None
        self._lock = threading.RLock()

    @log_operation
    def connect(self):
        with self._lock:
            if self.connected:
                return self
            try:
                import serial
            except ImportError as exc:
                raise ConfigurationError("Install embedded-test-framework[serial]") from exc
            try:
                self._serial = serial.serial_for_url(self.port, baudrate=self.baudrate,
                                                     timeout=self.timeout, write_timeout=self.timeout)
            except (OSError, serial.SerialException) as exc:
                raise TransportError("Cannot open serial port") from exc
            self.connected = True
            return self

    @log_operation
    def close(self):
        with self._lock:
            try:
                if self._serial is not None:
                    self._serial.close()
            finally:
                self._serial = None
                self.connected = False

    @log_operation
    def exchange(self, data, *, delimiter=b"\n", timeout=None):
        if not isinstance(data, bytes) or not isinstance(delimiter, bytes) or not delimiter:
            raise ConfigurationError("exchange requires bytes and a nonempty byte delimiter")
        duration = self.operation_timeout(timeout)
        with self._lock:
            self.require_connected()
            deadline = time.monotonic() + duration
            received = bytearray()
            try:
                self._serial.write_timeout = duration
                if self._serial.write(data) != len(data):
                    raise TransportError("Incomplete serial write")
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise OperationTimeout("Serial reply delimiter was not received")
                    self._serial.timeout = remaining
                    chunk = self._serial.read(1)
                    received.extend(chunk)
                    if received.endswith(delimiter):
                        return bytes(received)
            except TimeoutError as exc:
                raise OperationTimeout("Serial exchange timed out") from exc
            except OSError as exc:
                raise TransportError("Serial I/O failed") from exc
            finally:
                self._serial.timeout = self.timeout
                self._serial.write_timeout = self.timeout
