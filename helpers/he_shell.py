"""Common POSIX shell operations for devices that expose an SSH command engine."""

import logging
import shlex
from typing import Any

from embedded_framework.configurator.config_labels import LOGGERS

import logging
import shlex
from typing import Any

from embedded_framework.configurator.config_labels import LOGGERS


class CommandResult:
    """Normalized command result for shell execution."""

    def __init__(
        self,
        stdout: str = "",
        exit_status: int = 0,
        stderr: str = "",
    ) -> None:
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.exit_status = int(exit_status)

    def check(self) -> "CommandResult":
        if self.exit_status != 0:
            message = (
                f"Command failed with exit status {self.exit_status}. "
                f"stderr={self.stderr!r} stdout={self.stdout!r}"
            )
            raise RuntimeError(message)
        return self

    def __bool__(self) -> bool:
        return self.exit_status == 0

    def __str__(self) -> str:
        return self.stdout or self.stderr or ""


class ShellHelper:
    """Common POSIX shell operations executed through an SSH engine."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.logger = logging.getLogger(LOGGERS.HELPER)

    def _execute(self, command: str, timeout: float = 30) -> str:
        """Execute a command on the remote device."""
        self.logger.debug("Executing command: %s", command)
        return self.engine.do_command(command, time_out=timeout)

    @staticmethod
    def _path(path: str) -> str:
        """Validate and quote a remote path."""
        if not path or "\x00" in path:
            raise ValueError(
                "Remote path must be non-empty and contain no NUL characters"
            )

        # Prefix relative paths so names starting with '-' cannot become options.
        return shlex.quote(
            path if path.startswith("/") else "./" + path
        )

    def read_text(self, path: str, timeout: float = 30) -> str:
        """Read a remote text file."""
        return self._execute(
            f"cat {self._path(path)}",
            timeout,
        )

    def exists_file(self, path: str, timeout: float = 30) -> bool:
        """Return whether a regular remote file exists."""
        output = self._execute(
            f"test -f {self._path(path)} && echo 1 || echo 0",
            timeout,
        )
        return output.strip() == "1"

    def exists_dir(self, path: str, timeout: float = 30) -> bool:
        """Return whether a remote directory exists."""
        output = self._execute(
            f"test -d {self._path(path)} && echo 1 || echo 0",
            timeout,
        )
        return output.strip() == "1"

    def exists(self, path: str, timeout: float = 30) -> bool:
        """Return whether a remote path exists."""
        output = self._execute(
            f"test -e {self._path(path)} && echo 1 || echo 0",
            timeout,
        )
        return output.strip() == "1"

    def create_dir(
        self,
        path: str,
        timeout: float = 30,
    ) -> str:
        """Create a remote directory and missing parents."""
        return self._execute(
            f"mkdir -p {self._path(path)}",
            timeout,
        )

    def copy_file(
        self,
        source: str,
        destination: str,
        timeout: float = 30,
    ) -> str:
        """Copy a remote file."""
        return self._execute(
            f"cp {self._path(source)} {self._path(destination)}",
            timeout,
        )

    def move_file(
        self,
        source: str,
        destination: str,
        timeout: float = 30,
    ) -> str:
        """Move a remote file."""
        return self._execute(
            f"mv {self._path(source)} {self._path(destination)}",
            timeout,
        )

    def remove_file(
        self,
        path: str,
        timeout: float = 30,
    ) -> str:
        """Remove one remote file."""
        return self._execute(
            f"rm {self._path(path)}",
            timeout,
        )

    def _meminfo_kb(
        self,
        field: str,
        timeout: float = 30,
    ) -> int:
        """Read one numeric field from /proc/meminfo in KiB."""
        output = self._execute(
            f"awk '/^{field}:/ {{print $2}}' /proc/meminfo",
            timeout,
        ).strip()

        if not output:
            raise RuntimeError(
                f"{field} not found in /proc/meminfo"
            )

        return int(output)

    def get_total_memory(self, timeout: float = 30) -> int:
        """Return total system memory in KiB."""
        return self._meminfo_kb("MemTotal", timeout)

    def get_available_memory(self, timeout: float = 30) -> int:
        """Return estimated available system memory in KiB."""
        return self._meminfo_kb("MemAvailable", timeout)

    def get_free_memory(self, timeout: float = 30) -> int:
        """Return completely unused system memory in KiB."""
        return self._meminfo_kb("MemFree", timeout)

    def get_process_memory(
        self,
        pid: int,
        timeout: float = 30,
    ) -> int:
        """Return process resident memory (VmRSS) in KiB."""
        if pid <= 0:
            raise ValueError("pid must be positive")

        output = self._execute(
            f"awk '/^VmRSS:/ {{print $2}}' /proc/{pid}/status",
            timeout,
        ).strip()

        if not output:
            raise RuntimeError(
                f"VmRSS not found for process {pid}"
            )

        return int(output)

    def get_process_memory_by_name(
        self,
        name: str,
        timeout: float = 30,
    ) -> int:
        """Return total RSS in KiB for all matching processes."""
        if not name or "\x00" in name:
            raise ValueError(
                "Process name must be non-empty and contain no NUL characters"
            )

        output = self._execute(
            f"ps -C {shlex.quote(name)} -o rss= 2>/dev/null",
            timeout,
        )

        return sum(
            int(value)
            for value in output.split()
            if value.isdigit()
        )


if __name__ == "__main__":
    class FakeEngine:
        def do_command(
            self,
            command: str,
            time_out: float = 30,
        ) -> str:
            if "/proc/meminfo" in command:
                return "1024000\n"

            if "/proc/123/status" in command:
                return "20480\n"

            return ""

    helper = ShellHelper(FakeEngine())

    assert helper.get_total_memory() == 1024000
    assert helper.get_process_memory(123) == 20480

    print("self-check passed")