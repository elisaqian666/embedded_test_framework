from .base import CommandResult, Transport
from ..errors import TransportError


class MemoryTransport(Transport):
    """Explicit simulation; unknown commands fail rather than silently succeeding."""
    def __init__(self, responses=None, *, timeout=5.0):
        super().__init__(timeout)
        self.responses = dict(responses or {})
        self.history = []

    def connect(self):
        self.connected = True
        return self

    def close(self):
        self.connected = False

    def execute(self, command, *, timeout=None):
        self.require_connected()
        self.operation_timeout(timeout)
        self.history.append(command)
        if command not in self.responses:
            raise TransportError("No simulated response registered for command")
        value = self.responses[command]
        return value if isinstance(value, CommandResult) else CommandResult(command, stdout=str(value))
