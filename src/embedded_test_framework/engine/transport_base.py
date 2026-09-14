"""Communication lifecycle; legacy contract imports remain supported."""
from abc import ABC, abstractmethod
from ..core.contracts import CommandResult, HttpResponse, CommandChannel, RequestChannel, ByteChannel, FileChannel
from ..core.validation import positive_timeout
from ..errors import DeviceDisconnected
from ..logging import get_logger, log_operation


class Transport(ABC):
    """One owner per transport. Instances are not generally thread safe."""
    def __init__(self, timeout=5.0):
        self.logger = get_logger("engine", type(self).__name__)
        self.timeout = positive_timeout(timeout)
        self.connected = False

    def require_connected(self):
        if not self.connected:
            raise DeviceDisconnected("Transport is not connected")

    def operation_timeout(self, timeout):
        return self.timeout if timeout is None else positive_timeout(timeout)

    def disconnect(self):
        return self.close()

    @log_operation
    def reconnect(self):
        """Recover a connection explicitly without replaying any operation."""
        self.close()
        return self.connect()

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
