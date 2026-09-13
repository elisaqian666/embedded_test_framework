import pytest
from embedded_test_framework import FrameworkError, ConfigurationError, TransportError, OperationTimeout, CapabilityError, CleanupError


def test_public_error_contract():
    assert issubclass(OperationTimeout, TimeoutError)
    assert issubclass(OperationTimeout, TransportError)
    errors = [OSError("first"), RuntimeError("second")]
    cleanup = CleanupError(errors)
    errors.clear()
    assert len(cleanup.errors) == 2
    for error in (ConfigurationError(), TransportError(), OperationTimeout(), CapabilityError(), cleanup):
        with pytest.raises(FrameworkError):
            raise error
