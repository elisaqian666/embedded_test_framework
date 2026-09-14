"""Public SDK exceptions; original errors remain available through __cause__."""


class FrameworkError(Exception):
    code = "FRAMEWORK_ERROR"


class ConfigurationError(FrameworkError):
    code = "CONFIGURATION_ERROR"


class TransportError(FrameworkError):
    code = "TRANSPORT_ERROR"


class OperationTimeout(TransportError, TimeoutError):
    code = "OPERATION_TIMEOUT"


class CapabilityError(FrameworkError):
    code = "CAPABILITY_UNAVAILABLE"


class DeviceDisconnected(TransportError):
    code = "DEVICE_DISCONNECTED"


class CommandFailed(TransportError):
    code = "COMMAND_FAILED"

    def __init__(self, result):
        self.result = result
        self.exit_code = result.exit_code
        super().__init__(f"Command exited with status {result.exit_code}")


class ObservationFailed(FrameworkError, AssertionError):
    code = "OBSERVATION_FAILED"


class CleanupError(FrameworkError):
    code = "CLEANUP_FAILED"

    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__(f"Failed to close {len(self.errors)} resource(s)")
