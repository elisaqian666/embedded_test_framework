"""Android Debug Bridge communication."""

import math
import subprocess
import time

from embedded_test_framework.communication.base import BaseTransport
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import ADBCommandInvocationError


class AdbClient(BaseTransport):
    """Run commands on one Android device through the host ``adb`` executable."""

    def __init__(self, serial: str, executable: str = "adb", timeout: float = 30) -> None:
        if (
            not isinstance(serial, str)
            or not serial
            or not isinstance(executable, str)
            or not executable
            or isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
            or not math.isfinite(timeout)
        ):
            raise ValueError("ADB serial, executable, and positive timeout are required")
        self.serial, self.executable, self.timeout, self._connected = serial, executable, timeout, False

    def _run(self, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, "-s", self.serial, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout if timeout is None else timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ADBCommandInvocationError(
                f"ADB command {args!r} timed out after {error.timeout}s; stdout={error.stdout!r}; stderr={error.stderr!r}"
            ) from error
        except OSError as error:
            raise ADBCommandInvocationError(f"Cannot run {self.executable!r} {args!r}: {error}") from error

    def connect(self, timeout: float | None = None) -> None:
        budget = self.timeout if timeout is None else timeout
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0 or not math.isfinite(budget):
            raise ValueError("ADB timeout must be a finite positive number")
        self._connected = False
        result = self._run("get-state", timeout=budget)
        if result.returncode or result.stdout.strip() != "device":
            raise ADBCommandInvocationError(f"ADB device {self.serial!r} is unavailable: {result.stderr.strip() or result.stdout.strip()}")
        self._connected = True

    def disconnect(self) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def command(self, *args: str, timeout: float | None = None) -> CommandResult:
        """Run a raw ADB command and return its normalized result."""
        if not args or any(not isinstance(arg, str) or "\x00" in arg for arg in args) or not args[0] or args[0].startswith("-"):
            raise ValueError("ADB requires a subcommand and string arguments without NUL; global options come from configuration")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0 or not math.isfinite(timeout)
        ):
            raise ValueError("ADB command timeout must be positive")
        budget = self.timeout if timeout is None else timeout
        started = time.perf_counter()
        deadline = started + budget
        if not self.is_connected:
            raise ADBCommandInvocationError("ADB client is not connected; call connect() before executing commands")
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise ADBCommandInvocationError(f"ADB command {args!r} timed out after {budget}s before execution")
        result = self._run(*args, timeout=remaining)
        return CommandResult(result.stdout, result.returncode, result.stderr, duration=time.perf_counter() - started)

    def shell(self, command: str, *, timeout: float | None = None) -> CommandResult:
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise ValueError("ADB shell command must be non-empty and contain no NUL characters")
        return self.command("shell", command, timeout=timeout)

    execute = shell

    def close(self) -> None:
        self._connected = False

    def __enter__(self) -> "AdbClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def make_adb_client(serial: str, executable: str = "adb", timeout: float = 30) -> AdbClient:
    """Create and verify an ADB client for one Android device."""
    client = AdbClient(serial, executable, timeout)
    client.connect()
    return client
