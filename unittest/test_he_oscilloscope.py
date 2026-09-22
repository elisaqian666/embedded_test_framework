from unittest.mock import patch

from embedded_framework.helpers.he_oscilloscope import RigolOscilloscope


class _Socket:
    def __init__(self):
        self.sent = b""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def sendall(self, data):
        self.sent = data

    def recv(self, _):
        return b"RIGOL,DS1054Z,TEST,00.04\n"


def test_rigol_scpi_commands():
    connection = _Socket()
    with patch("embedded_framework.helpers.he_oscilloscope.socket.create_connection", return_value=connection):
        scope = RigolOscilloscope("192.0.2.1")
        scope.run()
        assert connection.sent == b":RUN\n"
        assert scope.identify() == "RIGOL,DS1054Z,TEST,00.04"
