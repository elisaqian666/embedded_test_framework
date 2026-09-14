import pytest
from embedded_test_framework.configurators import load_testconfig, load_device, ConfigurationUnderTest
from embedded_test_framework import ConfigurationError


def test_protocol_parameters(tmp_path, monkeypatch):
    monkeypatch.setenv("PASSWORD_FOR_TEST", "example")
    path = tmp_path / "testconfig.py"
    path.write_text('''
SSH = {"host": "192.168.1.103", "port": 2222, "password": "${PASSWORD_FOR_TEST}"}
SERIAL = {"port": "COM7", "baudrate": 57600}
ADB = {"executable": "C:/Android/adb.exe", "device": "board-1"}
FTP = {"host": "192.168.1.103", "remote_path": "/firmware.bin", "local_path": "out/firmware.bin"}
''', encoding="utf-8")
    document = load_testconfig(path)
    assert document["devices"]["dut"]["channels"]["console"]["baudrate"] == 57600
    device = ConfigurationUnderTest(path).create_device()
    assert not device.connected
    assert device._channels["shell"].port == 2222
    assert device._channels["console"].port == "COM7"
    assert device._channels["adb"].args == ["C:/Android/adb.exe", "-s", "board-1"]
    assert device.metadata["ftp_paths"]["local_path"] == str(tmp_path / "out/firmware.bin")


def test_full_inventory_and_lifecycle(tmp_path):
    path = tmp_path / "testconfig.py"
    path.write_text('TEST_CONFIG = {"devices": {"dut": {"channels": {"shell": {"type": "memory", "responses": {"version": "1.0"}}}}}}', encoding="utf-8")
    with load_device(path) as device:
        assert device.execute("version").stdout == "1.0"


@pytest.mark.parametrize("content", ["SSH = []", "TEST_CONFIG = []", "SSH = {'type': 'ssh'}", "METADATA = []", "FTP = {'remote_path': 1}", "raise RuntimeError('broken')"])
def test_invalid_python_configuration(tmp_path, content):
    path = tmp_path / "testconfig.py"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_device(path)
