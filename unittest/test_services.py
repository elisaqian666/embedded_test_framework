from unittest.mock import Mock, patch
import pytest
from embedded_test_framework.services import HealthService, SystemService, FileService
from embedded_test_framework import OperationTimeout, TransportError, CommandResult


def test_health_retries_transient_failure():
    service = HealthService(Mock())
    with patch.object(service, "check", side_effect=[TransportError("offline"), False, True]) as check:
        service.wait_ready(timeout=1, interval=0.001)
    assert check.call_count == 3


def test_health_timeout_preserves_cause():
    service = HealthService(Mock())
    error = TransportError("offline")
    with patch.object(service, "check", side_effect=error):
        with pytest.raises(OperationTimeout) as caught:
            service.wait_ready(timeout=0.001, interval=0.001)
    assert caught.value.__cause__ is error


def test_system_failure_and_file_routing():
    device = Mock()
    device.execute.return_value = CommandResult("version", exit_code=1)
    with pytest.raises(TransportError):
        SystemService(device).version()
    files = FileService(device, channel="firmware")
    files.download("remote", "local")
    device.download.assert_called_once_with("remote", "local", channel="firmware")
    files.upload("local", "remote")
    device.upload.assert_called_once_with("local", "remote", channel="firmware")
