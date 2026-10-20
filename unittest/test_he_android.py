from embedded_test_framework.helpers.he_android import AndroidHelper
from embedded_test_framework.lib.command_result import CommandResult


class FakeAdb:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def command(self, *args: str, timeout: float | None) -> CommandResult:
        self.calls.append(("command", args, timeout))
        return CommandResult("output")

    def shell(self, command: str, *, timeout: float | None) -> CommandResult:
        self.calls.append(("shell", command, timeout))
        return CommandResult("output")


def test_android_helper_delegates_adb_operations() -> None:
    adb = FakeAdb()
    helper = AndroidHelper(adb)

    assert helper.shell("getprop").stdout == "output"
    assert helper.logcat("-b", "main").stdout == "output"
    assert helper.logreport().stdout == "output"
    assert adb.calls == [
        ("shell", "getprop", None),
        ("command", ("logcat", "-d", "-b", "main"), None),
        ("command", ("bugreport",), None),
    ]


def test_android_command_and_shell_validate_check_before_sending():
    import pytest

    adb = FakeAdb()
    helper = AndroidHelper(adb)
    for operation in (lambda: helper.execute("getprop", check="false"), lambda: helper.command("devices", check=1)):
        with pytest.raises(TypeError, match="check must be bool"):
            operation()
    assert adb.calls == []
