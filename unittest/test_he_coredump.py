from pathlib import Path

from embedded_test_framework.helpers.he_coredump import CoreDumpHelper
from embedded_test_framework.lib.command_result import CommandResult


def test_collect_downloads_found_coredumps(tmp_path: Path) -> None:
    commands = []
    downloads = []

    def execute(command: str, timeout: float) -> CommandResult:
        commands.append((command, timeout))
        return CommandResult("/var/crash/core.app\n", 0)

    helper = CoreDumpHelper(execute, ("/var/crash",))
    collected = helper.collect(tmp_path, lambda remote, local: downloads.append((remote, local)))

    assert commands[0][1] == 10
    assert downloads == [("/var/crash/core.app", str(tmp_path))]
    assert collected == [tmp_path / "core.app"]


def test_scan_errors_are_not_treated_as_no_coredumps():
    import pytest

    helper = CoreDumpHelper(lambda *_: CommandResult("", 1, "Permission denied"), ("/var/crash",))
    with pytest.raises(RuntimeError, match="Permission denied"):
        helper.find()


def test_download_failure_preserves_detected_coredumps_and_tries_remaining_files(tmp_path, caplog):
    helper = CoreDumpHelper(lambda *_: CommandResult("/var/crash/core.first\n/var/crash/core.second\n"), ("/var/crash",))
    downloads = []

    def download(remote, local):
        downloads.append(remote)
        if remote.endswith("first"):
            raise OSError("download failed")

    assert helper.collect(tmp_path, download) == [tmp_path / "core.first", tmp_path / "core.second"]
    assert downloads == ["/var/crash/core.first", "/var/crash/core.second"]
    assert "download failed" in caplog.text
