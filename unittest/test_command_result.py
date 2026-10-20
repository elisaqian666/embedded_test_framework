import pytest
from embedded_test_framework.helpers.he_linux_host import CommandResult as LegacyCommandResult
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import SSHCommandError


def test_common_result_fields_and_legacy_import_are_shared():
    result = CommandResult(stdout="output", stderr="warning", exit_code=0, duration=0.125)
    assert LegacyCommandResult is CommandResult
    assert (result.stdout, result.stderr, result.exit_code, result.duration) == ("output", "warning", 0, 0.125)
    assert result.check() is result
    assert result
    assert str(result) == "output"


def test_exit_status_remains_a_writable_alias():
    result = CommandResult("partial", exit_status=7, stderr="denied")
    assert result.exit_code == result.exit_status == 7
    assert result.duration == 0
    assert not result
    with pytest.raises(SSHCommandError, match="denied"):
        result.check(SSHCommandError)
    result.exit_status = 0
    assert result.exit_code == 0
    result.exit_code = 2
    assert result.exit_status == 2
