from unittest.mock import patch

from embedded_framework.helpers.he_oscilloscope import RigolOscilloscope


class _Socket:
    def __init__(self, response):
        self.response, self.sent = bytearray(response), []

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        data, self.response = self.response[:size], self.response[size:]
        return bytes(data)

    def close(self):
        pass


def test_connect_and_run():
    connection = _Socket(b"RIGOL,DS1102Z-E,TEST,00.04\n")
    with patch.object(RigolOscilloscope, "ping", return_value=True), patch(
        "embedded_framework.helpers.he_oscilloscope.socket.create_connection", return_value=connection
    ):
        scope = RigolOscilloscope("192.0.2.1")
        scope.run()
        assert connection.sent == [b"*IDN?\n", b":RUN\n"]


def test_save_screenshot(tmp_path):
    image = b"\x89PNG\r\n"
    connection = _Socket(b"RIGOL,DS1102Z-E,TEST,00.04\n#16" + image + b"\n")
    with patch.object(RigolOscilloscope, "ping", return_value=True), patch(
        "embedded_framework.helpers.he_oscilloscope.socket.create_connection", return_value=connection
    ):
        target = RigolOscilloscope("192.0.2.1").save_screenshot(tmp_path / "capture.png")
        assert target.read_bytes() == image
        assert connection.sent[-1] == b":DISP:DATA? ON,OFF,PNG\n"
