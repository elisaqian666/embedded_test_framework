import hashlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from embedded_test_framework.helpers import ArtifactHelper, BuildHelper, ValgrindHelper, create_qr_code
from embedded_test_framework.hosts import DriverHelper, Peripheral
from embedded_test_framework.libs import Deadline
from embedded_test_framework import CommandResult, ConfigurationError, OperationTimeout, CapabilityError


def test_artifact_copy_and_hash(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"firmware")
    destination = ArtifactHelper.copy(source, tmp_path / "out" / "copy.bin")
    assert ArtifactHelper.sha256(destination) == hashlib.sha256(b"firmware").hexdigest()


def test_build_helper_returns_checked_result():
    host = Mock()
    host.run.return_value = CommandResult("build", stdout="done")
    assert BuildHelper(host).run(["make"], cwd="workspace").stdout == "done"
    host.run.assert_called_once_with(["make"], cwd="workspace", timeout=300)


def test_valgrind_quotes_program_arguments():
    device = Mock()
    ValgrindHelper(device).run(["/tmp/my app", "a;b"])
    command = device.execute.call_args.args[0]
    assert "'/tmp/my app' 'a;b'" in command
    assert "--error-exitcode=99" in command


def test_qr_optional_dependency_and_output(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "qrcode", None)
    with pytest.raises(ConfigurationError):
        create_qr_code("board", tmp_path / "board.png")
    image = Mock()
    module = SimpleNamespace(make=Mock(return_value=image))
    monkeypatch.setitem(sys.modules, "qrcode", module)
    path = create_qr_code("board", tmp_path / "images" / "board.png")
    module.make.assert_called_once_with("board")
    image.save.assert_called_once_with(path, format="PNG")


def test_host_driver_status():
    host = Mock()
    host.list_peripherals.return_value = [Peripheral("USB\\BOARD", "board", "USB", "OK")]
    assert DriverHelper(host).device_ready("usb\\board")
    with pytest.raises(CapabilityError):
        DriverHelper(host).device_status("missing")


def test_deadline_budget(monkeypatch):
    from embedded_test_framework.libs import timeout
    clock = [0.0]
    monkeypatch.setattr(timeout.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(timeout.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    budget = Deadline(2)
    assert budget.check() == 2
    budget.sleep(1)
    assert budget.remaining == 1
    with pytest.raises(OperationTimeout):
        budget.sleep(5)
    assert budget.expired
