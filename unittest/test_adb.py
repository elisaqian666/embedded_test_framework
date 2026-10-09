import subprocess

from embedded_test_framework.communication.adb import make_adb_client


def test_adb_client_checks_device_and_executes_shell(monkeypatch) -> None:
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "device\n" if command[-1] == "get-state" else "Android\n", "")

    monkeypatch.setattr("embedded_test_framework.communication.adb.subprocess.run", run)
    client = make_adb_client("emulator-5554")

    assert client.is_connected
    assert client.shell("getprop ro.product.name").stdout == "Android\n"
    assert commands == [
        ["adb", "-s", "emulator-5554", "get-state"],
        ["adb", "-s", "emulator-5554", "shell", "getprop ro.product.name"],
    ]
