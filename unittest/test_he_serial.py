import pytest

from embedded_test_framework.helpers.he_serial import SerialHelper


class FakeSerial:
    def __init__(self):
        self.sent = []

    def write(self, data):
        self.sent.append(data)
        return len(data)


def test_serial_command_frames():
    engine = FakeSerial()
    helper = SerialHelper(engine)
    assert helper.send_command("AT", eol="\r\n") == 4
    helper.send_command("status", eol="\n")
    helper.send_command("AT", eol="\r")
    helper.send_command("AA 00 ff", hex_mode=True)
    helper.send_command("AA00ff", hex_mode=True, eol=b"\r")
    helper.send_command(b"\x00\xff\x0a")
    helper.send_command("温度", encoding="gbk")
    helper.send_command("", eol="\r")
    assert engine.sent == [b"AT\r\n", b"status\n", b"AT\r", b"\xaa\x00\xff", b"\xaa\x00\xff\r", b"\x00\xff\x0a", "温度".encode("gbk"), b"\r"]


@pytest.mark.parametrize("command, options, error", [
    ("GG", {"hex_mode": True}, ValueError),
    ("ABC", {"hex_mode": True}, ValueError),
    (b"AA", {"hex_mode": True}, TypeError),
    ([1, 2], {}, TypeError),
    ("AT", {"eol": True}, TypeError),
    ("AT", {"hex_mode": "false"}, TypeError),
    ("", {}, ValueError),
    ("温度", {"encoding": "ascii"}, UnicodeEncodeError),
])
def test_invalid_commands_do_not_write(command, options, error):
    engine = FakeSerial()
    with pytest.raises(error):
        SerialHelper(engine).send_command(command, **options)
    assert engine.sent == []


def test_partial_write_is_not_retried():
    engine = FakeSerial()

    def partial_write(data):
        engine.sent.append(data)
        return 1

    engine.write = partial_write
    with pytest.raises(OSError, match="Incomplete serial write"):
        SerialHelper(engine).send_command("AT")
    assert engine.sent == [b"AT"]
