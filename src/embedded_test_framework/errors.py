"""Public SDK exceptions; original errors remain available through __cause__."""


class FrameworkError(Exception):
    pass


class ConfigurationError(FrameworkError):
    pass


class TransportError(FrameworkError):
    pass


class OperationTimeout(TransportError, TimeoutError):
    pass


class CapabilityError(FrameworkError):
    pass


class CleanupError(FrameworkError):
    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__(f"Failed to close {len(self.errors)} resource(s)")
