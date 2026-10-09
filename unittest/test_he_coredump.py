from pathlib import Path

from embedded_test_framework.helpers.he_coredump import CoreDumpHelper
from embedded_test_framework.helpers.he_shell import CommandResult


def test_collect_downloads_found_coredumps(tmp_path: Path) -> None:
    commands = []
    downloads = []

    def execute(command: str, timeout: float) -> CommandResult:
        commands.append((command, timeout))
        return CommandResult("/var/crash/core.app\n", 0)

    helper = CoreDumpHelper(execute, ("/var/crash",))
    collected = helper.collect(tmp_path, lambda remote, local: downloads.append((remote, local)))

    assert "find /var/crash" in commands[0][0]
    assert downloads == [("/var/crash/core.app", str(tmp_path))]
    assert collected == [tmp_path / "core.app"]
