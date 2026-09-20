"""Coredump detection for devices that expose a command executor."""

import shlex
import logging
from collections.abc import Callable
from embedded_framework.configurator.config_labels import LOGGERS
from embedded_framework.helpers.he_shell import CommandResult


class CoreDumpHelper:
    """Detect coredumps on a remote device."""

    def __init__(
        self,
        execute: Callable[[str, float], CommandResult],
        paths: tuple[str, ...],
        pattern: str = "core*",
    ) -> None:
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

        result = self._execute(
            f"find {paths} -type f -name {pattern} 2>/dev/null",
            timeout,
        )

        if result.exit_status not in (0, 1):
            result.check()

        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

    def exists(self, timeout: float = 10) -> bool:
        """Return whether at least one coredump exists."""
        return bool(self.find(timeout))


if __name__ == "__main__":
    def fake_execute(command: str, timeout: float) -> CommandResult:
        assert "find" in command
        assert "'core_*.gz'" in command

        return CommandResult(
            stdout=(
                "/store/core_usr!bin!app.gz\n"
                "/misc/coredumps/core_test.gz\n"
            ),
            exit_status=0,
        )

    helper = CoreDumpHelper(
        fake_execute,
        paths=("/store", "/misc/coredumps"),
        pattern="core_*.gz",
    )

    assert helper.find() == [
        "/store/core_usr!bin!app.gz",
        "/misc/coredumps/core_test.gz",
    ]

    print("self-check passed")