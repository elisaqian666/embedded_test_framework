"""Common POSIX shell operations for devices that expose a command executor."""

import shlex
from collections.abc import Callable
from dataclasses import dataclass

from embedded_framework.lib.custom_exception import EmbeddedFrameworkException


@dataclass(frozen=True)
class CommandResult:
    """Transport-independent command output, using the existing SSH result fields."""

    stdout: str
    exit_status: int
    stderr: str = ""

    def check(self) -> "CommandResult":
        """Raise CommandError for a failed command; otherwise return this result."""
        if self.exit_status:
            raise CommandError(self)
        return self


class CommandError(EmbeddedFrameworkException):
    """A non-zero command exit status; full output is available through result."""

    def __init__(self, result: CommandResult) -> None:
        super().__init__(f"Device command failed with exit status {result.exit_status}")
        self.result = result


class ShellHelper:
    """Subset of LinuxCommandsSsh's common file operations, with quoted path arguments.

    :param execute: Callable accepting (command, timeout), returning CommandResult.
    """

    def __init__(self, execute: Callable[[str, float], CommandResult]) -> None:
        self._execute = execute

    @staticmethod
    def _path(path: str) -> str:
        if not path or "\x00" in path:
            message = "Remote path must be non-empty and contain no NUL characters"
            raise ValueError(message)
        # Prefix relative paths so names starting with '-' cannot become options.
        return shlex.quote(path if path.startswith("/") else "./" + path)

    def read_text(self, path: str, timeout: float = 30) -> str:
        """Read a remote file; raise on command failure."""
        return self._execute(f"cat {self._path(path)}", timeout).check().stdout

    def exists_file(self, path: str, timeout: float = 30) -> bool:
        """Return whether a regular remote file exists; do not suppress transport errors."""
        result = self._execute(f"test -f {self._path(path)}", timeout)
        if result.exit_status not in (0, 1):
            result.check()
        return result.exit_status == 0

    def exists_dir(self, path: str, timeout: float = 30) -> bool:
        """Return whether a remote directory exists."""
        result = self._execute(f"test -d {self._path(path)}", timeout)
        if result.exit_status not in (0, 1):
            result.check()
        return result.exit_status == 0

    def exists(self, path: str, timeout: float = 30) -> bool:
        """Return whether a remote path exists, regardless of file type."""
        result = self._execute(f"test -e {self._path(path)}", timeout)
        if result.exit_status not in (0, 1):
            result.check()
        return result.exit_status == 0

    def create_dir(self, path: str, timeout: float = 30) -> CommandResult:
        """Create remote directories using the device's normal umask."""
        return self._execute(f"mkdir -p {self._path(path)}", timeout).check()

    def copy_file(self, source: str, destination: str, timeout: float = 30) -> CommandResult:
        """Copy a remote file without interpreting either path as shell syntax."""
        return self._execute(f"cp {self._path(source)} {self._path(destination)}", timeout).check()

    def move_file(self, source: str, destination: str, timeout: float = 30) -> CommandResult:
        """Move a remote file."""
        return self._execute(f"mv {self._path(source)} {self._path(destination)}", timeout).check()

    def remove_file(self, path: str, timeout: float = 30) -> CommandResult:
        """Remove one remote file; no recursive directory deletion is exposed."""
        return self._execute(f"rm {self._path(path)}", timeout).check()
