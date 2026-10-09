"""Android Debug Bridge communication."""

import subprocess

from embedded_test_framework.communication.base import BaseTransport
from embedded_test_framework.helpers.he_shell import CommandResult


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
        ):
            raise ValueError("ADB serial, executable, and positive timeout are required")
        self.serial, self.executable, self.timeout, self._connected = serial, executable, timeout, False

    def _run(self, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.executable, "-s", self.serial, *args], capture_output=True, text=True, timeout=timeout or self.timeout, check=False
            )
        except FileNotFoundError as error:
            raise ConnectionError(f"ADB executable not found: {self.executable}") from error
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"ADB command timed out: {' '.join(args)}") from error

    def connect(self) -> None:
        result = self._run("get-state")
        if result.returncode or result.stdout.strip() != "device":
            raise ConnectionError(f"ADB device {self.serial!r} is unavailable: {result.stderr.strip() or result.stdout.strip()}")
        self._connected = True

    def disconnect(self) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def command(self, *args: str, timeout: float | None = None) -> CommandResult:
        """Run a raw ADB command and return its normalized result."""
        if not args or any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in args):
            raise ValueError("ADB command arguments must be non-empty strings without NUL characters")
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
            raise ValueError("ADB command timeout must be positive")
        if not self.is_connected:
            self.connect()
        result = self._run(*args, timeout=timeout)
        return CommandResult(result.stdout, result.returncode, result.stderr)

    def shell(self, command: str, *, timeout: float | None = None) -> CommandResult:
        if not isinstance(command, str) or not command or "\x00" in command:
            raise ValueError("ADB shell command must be non-empty and contain no NUL characters")
        return self.command("shell", command, timeout=timeout)

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
