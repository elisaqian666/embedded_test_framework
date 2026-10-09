from embedded_test_framework.helpers.he_android import AndroidHelper
from embedded_test_framework.helpers.he_shell import CommandResult


class FakeAdb:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def command(self, *args: str, timeout: float) -> CommandResult:
        self.calls.append(("command", args, timeout))
        return CommandResult("output")

    def shell(self, command: str, *, timeout: float) -> CommandResult:
        self.calls.append(("shell", command, timeout))
        return CommandResult("output")


def test_android_helper_delegates_adb_operations() -> None:
    adb = FakeAdb()
    helper = AndroidHelper(adb)

    assert helper.shell("getprop").stdout == "output"
    assert helper.logcat("-b", "main").stdout == "output"
    assert helper.logreport().stdout == "output"
    assert adb.calls == [
        ("shell", "getprop", 30),
        ("command", ("logcat", "-d", "-b", "main"), 30),
        ("command", ("bugreport",), 120),
    ]
