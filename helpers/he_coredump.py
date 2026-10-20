"""Coredump detection for devices that expose a command executor."""

import logging
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

from embedded_test_framework.configurator.config_labels import LOGGERS
from embedded_test_framework.lib.command_result import CommandResult


class CoreDumpHelper:
    """Detect coredumps on a remote device."""

    DEFAULT_PATHS = ("/var/lib/systemd/coredump", "/var/crash", "/tmp/")

    def __init__(self, execute: Callable[[str, float], CommandResult], paths: tuple[str, ...], pattern: str = "core*") -> None:
        if not paths:
            raise ValueError("At least one coredump path is required")

        if not pattern:
            raise ValueError("Coredump pattern must not be empty")

        self._execute = execute
        self._paths = paths
        self._pattern = pattern
        self.logger = logging.getLogger(LOGGERS.HELPER)

    def find(self, timeout: float = 10) -> list[str]:
        """Return coredump paths found on the device."""

        paths = " ".join(shlex.quote(path) for path in self._paths)
        pattern = shlex.quote(self._pattern)

        command = (
            f"for dir in {paths}; do "
            f'[ -d "$dir" ] || continue; '
            f'find "$dir" -type f -name {pattern} || exit $?; '
            f"done"
        )

        result = self._execute(command, timeout)
        result.check()
        files = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        self.logger.info("Found %d coredump files: %s", len(files), files)
        return files

    # def find(self, timeout: float = 10) -> list[str]:
    #     """Return coredump paths found on the device."""
    #     paths = " ".join(shlex.quote(path) for path in self._paths)
    #     pattern = shlex.quote(self._pattern)
    #
    #     result = self._execute(f"find {paths} -type f -name {pattern}", timeout)
    #     self.logger.info("Coredump search result: %s", result)
    #
    #     result.check()
    #
    #     return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def exists(self, timeout: float = 10) -> bool:
        """Return whether at least one coredump exists."""
        return bool(self.find(timeout))

    def collect(self, destination: str | Path, download: Callable[[str, str], Any], timeout: float = 10) -> list[Path]:
        """Return detected artifact paths even if downloads fail; scan errors propagate."""
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        files = self.find(timeout)
        for remote_path in files:
            self.logger.info("Collecting coredump %s into %s", remote_path, destination)
            try:
                download(remote_path, str(destination))
            except Exception:
                self.logger.exception("Unable to download detected coredump %s", remote_path)
        return [destination / Path(remote_path).name for remote_path in files]


if __name__ == "__main__":

    def fake_execute(command: str, timeout: float) -> CommandResult:
        assert "find" in command
        assert "'core_*.gz'" in command

        return CommandResult(stdout=("/store/core_usr!bin!app.gz\n" "/misc/coredumps/core_test.gz\n"), exit_status=0)

    helper = CoreDumpHelper(fake_execute, paths=("/store", "/misc/coredumps"), pattern="core_*.gz")

    assert helper.find() == ["/store/core_usr!bin!app.gz", "/misc/coredumps/core_test.gz"]

    print("self-check passed")
