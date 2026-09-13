from ..logging import log_operation
"""Command transports backed by installed OpenSSH and Android platform tools."""
import subprocess
import time

from .base import CommandResult, Transport
from ..errors import ConfigurationError, OperationTimeout, TransportError


class ProcessTransport(Transport):
    def _run(self, args, command, timeout):
        started = time.monotonic()
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=self.operation_timeout(timeout), shell=False)
        except subprocess.TimeoutExpired as exc:
            raise OperationTimeout("Remote command timed out") from exc
        except OSError as exc:
            raise TransportError("Cannot start command client; check executable and PATH") from exc
        return CommandResult(command, result.stdout, result.stderr, result.returncode, time.monotonic() - started)

    @log_operation
    def close(self):
        self.connected = False


class SSHTransport(ProcessTransport):
    """OpenSSH key/agent authentication, or optional Paramiko password session."""
    def __init__(self, host, username="root", *, port=22, key_filename=None, password=None, timeout=30.0):
        super().__init__(timeout)
        if not host or host.startswith("-") or not username or username.startswith("-"):
            raise ConfigurationError("Invalid SSH host or username")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ConfigurationError("Invalid SSH port")
        self.args = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-p", str(port)]
        if key_filename:
            self.args += ["-i", str(key_filename)]
        self.args += [f"{username}@{host}"]
        self.host, self.username, self.port = host, username, port
        self._password = password
        self._client = None

    @log_operation
    def connect(self):
        if not self.connected:
            if self._password is None:
                self._run(self.args + ["true"], "true", None).check()
            else:
                try:
                    import paramiko
                except ImportError as exc:
                    raise ConfigurationError("Install embedded-test-framework[ssh] for password authentication") from exc
                client = paramiko.SSHClient()
                try:
                    client.load_system_host_keys()
                    client.set_missing_host_key_policy(paramiko.RejectPolicy())
                    client.connect(self.host, port=self.port, username=self.username, password=self._password,
                                   timeout=self.timeout, auth_timeout=self.timeout, banner_timeout=self.timeout,
                                   look_for_keys=False, allow_agent=False)
                except Exception as exc:
                    client.close()
                    raise TransportError("SSH password connection failed; check host key and credentials") from exc
                self._client = client
            self.connected = True
        return self

    @log_operation
    def execute(self, command, *, timeout=None):
        self.require_connected()
        if self._client is not None:
            duration = self.operation_timeout(timeout)
            started = time.monotonic()
            channel = None
            try:
                channel = self._client.get_transport().open_session(timeout=duration)
                channel.settimeout(max(0.001, duration - (time.monotonic() - started)))
                channel.exec_command(command)
                out, err = bytearray(), bytearray()
                while True:
                    if time.monotonic() - started >= duration:
                        raise OperationTimeout("SSH command timed out")
                    if channel.recv_ready():
                        out.extend(channel.recv(65536))
                    if channel.recv_stderr_ready():
                        err.extend(channel.recv_stderr(65536))
                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        return CommandResult(command, out.decode("utf-8", errors="replace"),
                                             err.decode("utf-8", errors="replace"), channel.recv_exit_status(),
                                             time.monotonic() - started)
                    time.sleep(min(0.01, max(0, duration - (time.monotonic() - started))))
            except TimeoutError as exc:
                raise OperationTimeout("SSH command timed out") from exc
            except Exception as exc:
                raise TransportError("SSH command failed") from exc
            finally:
                if channel is not None:
                    channel.close()
        return self._run(self.args + [command], command, timeout)

    @log_operation
    def close(self):
        try:
            if self._client is not None:
                self._client.close()
        finally:
            self._client = None
            self.connected = False


class ADBTransport(ProcessTransport):
    def __init__(self, device=None, *, timeout=30.0):
        super().__init__(timeout)
        self.args = ["adb"] + (["-s", device] if device else [])

    @log_operation
    def connect(self):
        if not self.connected:
            result = self._run(self.args + ["get-state"], "get-state", None).check()
            if result.stdout.strip() != "device":
                raise TransportError("ADB device is not ready")
            self.connected = True
        return self

    @log_operation
    def execute(self, command, *, timeout=None):
        self.require_connected()
        return self._run(self.args + ["shell", command], command, timeout)
