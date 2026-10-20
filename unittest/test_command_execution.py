import logging
import subprocess
import threading
import time
from collections import deque
from unittest.mock import Mock

import pytest
from embedded_test_framework.communication.adb import AdbClient
from embedded_test_framework.communication.ssh import SshTransport
from embedded_test_framework.configurator.configurator_dut import ConnectionConfig, DeviceConfig, EngineFactory
from embedded_test_framework.devices.linux import LinuxDevice
from embedded_test_framework.helpers.he_android import AndroidHelper
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import ADBCommandInvocationError, SSHCommandError


@pytest.mark.parametrize(
    "command",
    ['echo "a b" | cat', "getprop ro.product.name", "adb devices"],
)
def test_adb_execute_is_literal_device_shell_and_returns_result(monkeypatch, command):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "output\n", "warning"))
    monkeypatch.setattr(subprocess, "run", run)
    client = AdbClient("target")
    client._connected = True
    result = AndroidHelper(client).execute(command, timeout=2)
    assert isinstance(result, CommandResult)
    assert (result.stdout, result.stderr, result.exit_code) == ("output\n", "warning", 0)
    assert run.call_args.args[0] == ["adb", "-s", "target", "shell", command]
    assert 0 < run.call_args.kwargs["timeout"] <= 2
    assert run.call_args.kwargs["encoding"] == "utf-8"


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess([], 1, "partial", "permission denied"),
        subprocess.TimeoutExpired("adb", 2, output=b"partial", stderr=b"slow"),
        FileNotFoundError("missing adb"),
    ],
)
def test_adb_failures_are_typed_and_diagnostic(monkeypatch, failure):
    run = Mock()
    if isinstance(failure, Exception):
        run.side_effect = failure
    else:
        run.return_value = failure
    monkeypatch.setattr(subprocess, "run", run)
    client = AdbClient("target")
    client._connected = True
    with pytest.raises(ADBCommandInvocationError) as caught:
        AndroidHelper(client).execute("false", timeout=2)
    if isinstance(failure, Exception):
        assert "false" in str(caught.value)
    else:
        assert "permission denied" in str(caught.value) and "partial" in str(caught.value)
    assert run.call_count == 1


class Channel:
    def __init__(self, status=0, done=True):
        self.output = deque([b"part1", b"part2"])
        self.errors = deque([b"diagnostic"])
        self.status, self.done, self.closed = status, done, False

    def recv_ready(self):
        return bool(self.output)

    def recv_stderr_ready(self):
        return bool(self.errors)

    def recv(self, size):
        return self.output.popleft()

    def recv_stderr(self, size):
        return self.errors.popleft()

    def exit_status_ready(self):
        return self.done and not self.output and not self.errors

    @property
    def eof_received(self):
        return self.exit_status_ready()

    def recv_exit_status(self):
        return self.status

    def shutdown_write(self):
        pass

    def close(self):
        self.closed = True


def transport(channel):
    ssh = SshTransport.__new__(SshTransport)
    ssh._lock = threading.RLock()
    ssh.timeout = 60
    ssh.logger = logging.getLogger("ssh-test")
    ssh.ssh_con = Mock()
    ssh.ssh_con.exec_command.return_value = (Mock(), Mock(channel=channel), Mock())
    return ssh


def test_ssh_drains_both_streams_and_returns_stdout():
    channel = Channel()
    ssh = transport(channel)
    assert ssh.execute("command", timeout=1).stdout == "part1part2"
    assert channel.closed
    assert ssh.ssh_con.exec_command.call_count == 1


def test_transport_result_retains_nonzero_status_and_measures_duration(monkeypatch):
    ssh = transport(Channel())

    def completed(command, timeout):
        time.sleep(0.005)
        return "partial", 3, "failed"

    monkeypatch.setattr(ssh, "_ssh_exec_command_w_timeout", completed)
    result = ssh.exec_command("command", timeout=1)
    assert isinstance(result, CommandResult)
    assert (result.stdout, result.stderr, result.exit_code) == ("partial", "failed", 3)
    assert result.duration >= 0.005


def test_linux_shell_uses_transport_result_and_checks_failures():
    ssh = transport(Channel(status=7))
    config = DeviceConfig("linux", {"ssh": ConnectionConfig("ssh")}, "ssh")
    device = LinuxDevice(config, EngineFactory())
    device._connected = True
    device._engines["ssh"] = ssh
    result = device.shell("command", timeout=1, check=False)
    assert (result.stdout, result.exit_code, result.stderr) == ("part1part2", 7, "diagnostic")
    assert result.duration >= 0
    ssh.ssh_con.exec_command.return_value = (Mock(), Mock(channel=Channel(status=7)), Mock())
    with pytest.raises(SSHCommandError, match="diagnostic"):
        device.shell("command", timeout=1)


def test_ssh_exit_failure_and_raw_status():
    ssh = transport(Channel(status=7))
    with pytest.raises(SSHCommandError, match="diagnostic"):
        ssh.do_command("bad", time_out=1)
    assert transport(Channel(status=7)).do_command_w_exitstatus("bad", time_out=1) == ("part1part2", 7, "diagnostic")


def test_ssh_timeout_is_short_closes_channel_and_does_not_retry():
    channel = Channel(done=False)
    ssh = transport(channel)
    with pytest.raises(SSHCommandError, match="timed out") as caught:
        ssh.execute("sleep 60", timeout=0.02)
    assert "part1part2" in str(caught.value)
    assert channel.closed
    assert ssh.ssh_con.exec_command.call_count == 1


def test_ssh_connection_failure_and_missing_exit_status():
    ssh = transport(Channel())
    ssh.ssh_con.exec_command.side_effect = OSError("connection lost")
    with pytest.raises(SSHCommandError, match="connection lost"):
        ssh.execute("command", timeout=1)
    assert ssh.ssh_con.exec_command.call_count == 1
    with pytest.raises(SSHCommandError, match="without an exit status"):
        transport(Channel(status=-1)).execute("command", timeout=1)


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf")])
def test_invalid_timeouts_never_execute(timeout):
    with pytest.raises(ValueError):
        AdbClient("target").execute("adb devices", timeout=timeout)
    ssh = transport(Channel())
    with pytest.raises(ValueError):
        ssh.execute("true", timeout=timeout)
    ssh.ssh_con.exec_command.assert_not_called()


def test_legacy_ssh_entry_returns_complete_stdout_and_checks_exit_status():
    ssh = transport(Channel())
    assert ssh.do_ssh_command("command", time_out=1, rcvd_timeout=0.5) == "part1part2"
    assert ssh.ssh_con.exec_command.call_count == 1
    assert 0 < ssh.ssh_con.exec_command.call_args.kwargs["timeout"] <= 0.5
    with pytest.raises(SSHCommandError, match="diagnostic"):
        transport(Channel(status=7)).do_ssh_command("bad", time_out=1)


def test_legacy_ssh_entry_uses_shared_timeout_and_cleanup():
    channel = Channel(done=False)
    ssh = transport(channel)
    with pytest.raises(SSHCommandError, match="timed out"):
        ssh.do_ssh_command("sleep 60", time_out=1, rcvd_timeout=0.02)
    assert channel.closed
    assert ssh.ssh_con.exec_command.call_count == 1


@pytest.mark.parametrize("receive_timeout", [0, -1, True, float("nan"), "1"])
def test_legacy_ssh_entry_rejects_invalid_receive_timeout(receive_timeout):
    ssh = transport(Channel())
    with pytest.raises(ValueError):
        ssh.do_ssh_command("command", rcvd_timeout=receive_timeout)
    ssh.ssh_con.exec_command.assert_not_called()


def test_ssh_readiness_uses_checked_path_and_restores_logging(monkeypatch):
    ssh = transport(Channel())
    ssh.pause_logging = Mock()
    ssh.resume_logging = Mock()

    def wait(command, timeout, exception, *args, **kwargs):
        assert command == ssh.do_command
        assert exception is SSHCommandError
        assert args == (":",)
        assert kwargs == {"time_out": 3}
        raise SSHCommandError("not ready")

    monkeypatch.setattr("embedded_test_framework.communication.ssh.wait_no_exception_timeout", wait)
    with pytest.raises(SSHCommandError, match="not ready"):
        ssh.wait_for_ssh_server_responsive(timeout=3)
    ssh.resume_logging.assert_called_once_with()


@pytest.mark.parametrize("error_type", [FileNotFoundError, OSError])
def test_scp_upload_failure_never_deletes_or_replays(error_type, monkeypatch):
    scp_client = Mock()
    failure = error_type("upload failed")
    scp_client.put.side_effect = failure
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=scp_client)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("embedded_test_framework.communication.ssh.scp.SCPClient", factory)
    ssh = transport(Channel())
    ssh.__re_init__ = Mock()
    destination = "/store/old file; unexpected shell syntax"

    with pytest.raises(error_type) as caught:
        ssh.put_files("missing file", destination)
    assert caught.value is failure
    scp_client.put.assert_called_once_with("missing file", destination, recursive=True, preserve_times=False)
    ssh.ssh_con.exec_command.assert_not_called()
    ssh.__re_init__.assert_not_called()
    factory.assert_called_once()


def test_ssh_factory_timeout_is_inherited_by_device_helper_and_legacy_api(monkeypatch):
    session = Mock()
    monkeypatch.setattr("embedded_test_framework.communication.ssh.create_ssh_session_obj_from_hostname", Mock(return_value=session))
    budgets = []

    def complete(self, command, timeout):
        budgets.append(timeout)
        return "out", 7, "failed"

    monkeypatch.setattr(SshTransport, "_ssh_exec_command_w_timeout", complete)
    config = DeviceConfig(
        "board", {"control": ConnectionConfig("ssh", {"address": "board", "username": "user", "password": "test", "timeout": 4})}, "control"
    )
    with LinuxDevice(config, EngineFactory()) as device:
        helper = device.linux_host()
        raw = device.engine()
        assert raw.timeout == 4
        assert device.execute("false", check=False).exit_code == 7
        assert helper.execute("false", timeout=2, check=False).exit_code == 7
        assert raw.execute("false").exit_code == 7
        with pytest.raises(SSHCommandError):
            raw.do_command("false")
        assert 0 < budgets[0] <= 4
        assert 0 < budgets[1] <= 2
        assert all(0 < budget <= 4 for budget in budgets[2:])


def test_adb_timeout_inheritance_explicit_argv_and_raw_results(monkeypatch):
    from embedded_test_framework.devices.android import AndroidDevice

    run = Mock(
        side_effect=lambda argv, **kwargs: (
            subprocess.CompletedProcess(argv, 0, "device", "")
            if argv[-1] == "get-state"
            else subprocess.CompletedProcess(argv, 7, "partial", "denied")
        )
    )
    monkeypatch.setattr(subprocess, "run", run)
    config = DeviceConfig("board", {"usb": ConnectionConfig("adb", {"serial": "target", "timeout": 4})}, "usb")
    with AndroidDevice(config, EngineFactory()) as device:
        helper = device.adb()
        raw = device.engine()
        assert device.execute("false", check=False).exit_code == 7
        assert 0 < run.call_args.kwargs["timeout"] <= 4
        with pytest.raises(ADBCommandInvocationError, match="denied"):
            helper.execute("false", timeout=2)
        assert 0 < run.call_args.kwargs["timeout"] <= 2
        result = raw.execute("false")
        assert (result.stdout, result.stderr, result.exit_code) == ("partial", "denied", 7)
        result = helper.command("push", "local file", "/sdcard/file", timeout=3, check=False)
        assert result.exit_code == 7
        assert run.call_args.args[0] == ["adb", "-s", "target", "push", "local file", "/sdcard/file"]
    count = run.call_count
    with pytest.raises(ADBCommandInvocationError, match="not connected"):
        raw.execute("getprop")
    assert run.call_count == count


@pytest.mark.parametrize("args", [("-s", "another-device"), ("--help",), ("",), ("shell", "bad\x00value")])
def test_adb_raw_command_cannot_override_device_selection(args, monkeypatch):
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    client = AdbClient("target")
    client._connected = True
    with pytest.raises(ValueError):
        client.command(*args)
    run.assert_not_called()
