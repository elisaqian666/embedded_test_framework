"""Offline tests for engine/transport_base, command, ftp, http, memory and serial."""
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import urllib.error

import pytest

from embedded_test_framework.engine import ADBTransport, SSHTransport, FTPTransport, HttpTransport, SerialTransport, MemoryTransport, CommandResult, HttpResponse
from embedded_test_framework.errors import ConfigurationError, OperationTimeout, TransportError


def test_results_and_memory_context():
    assert HttpResponse(201, {}, b'{"ok":true}').json() == {"ok": True}
    assert not HttpResponse(500, {}, b'').ok
    failed = CommandResult("bad", exit_code=3)
    with MemoryTransport({"bad": failed}) as engine:
        assert engine.execute("bad") is failed
        with pytest.raises(TransportError):
            failed.check()
    assert not engine.connected


@pytest.mark.parametrize("engine", [SSHTransport("board"), ADBTransport("serial-1")])
def test_command_execution_and_timeout(engine):
    with patch("embedded_test_framework.engine.command.subprocess.run", return_value=SimpleNamespace(stdout="device\n", stderr="", returncode=0)) as run:
        engine.connect()
        assert engine.execute("echo hello").ok
        assert run.call_args.kwargs["shell"] is False
        assert run.call_args.args[0][-1] == "echo hello"
    with patch("embedded_test_framework.engine.command.subprocess.run", side_effect=subprocess.TimeoutExpired("client", 1)):
        with pytest.raises(OperationTimeout):
            engine.execute("sleep 10", timeout=1)
    engine.close()
    with pytest.raises(TransportError):
        engine.execute("echo hello")


def test_adb_rejects_offline_state():
    engine = ADBTransport()
    with patch.object(engine, "_run", return_value=CommandResult("get-state", "offline")):
        with pytest.raises(TransportError):
            engine.connect()
    assert not engine.connected


def test_ftp_roundtrip_and_cleanup(tmp_path):
    client = Mock()
    client.retrbinary.side_effect = lambda command, callback: callback(b"firmware")
    with patch("embedded_test_framework.engine.ftp.FTP", return_value=client):
        with FTPTransport("board") as engine:
            path = engine.download("image.bin", tmp_path / "image.bin")
            assert path.read_bytes() == b"firmware"
            client.storbinary.side_effect = lambda command, stream: client.sent(stream.read())
            engine.upload(path, "image.bin")
            client.sent.assert_called_once_with(b"firmware")
        client.close.assert_called_once()


def test_ftp_failed_login_releases_client():
    client = Mock()
    client.login.side_effect = OSError("offline")
    with patch("embedded_test_framework.engine.ftp.FTP", return_value=client):
        engine = FTPTransport("board")
        with pytest.raises(TransportError):
            engine.connect()
        client.close.assert_called_once()
        assert not engine.connected


def test_http_network_failure_and_timeout():
    with HttpTransport("http://board") as engine:
        opener = Mock()
        with patch("embedded_test_framework.engine.http.urllib.request.build_opener", return_value=opener):
            opener.open.side_effect = urllib.error.URLError(TimeoutError())
            with pytest.raises(OperationTimeout):
                engine.request("GET", "/")
            opener.open.side_effect = urllib.error.URLError("offline")
            with pytest.raises(TransportError):
                engine.request("GET", "/")


def test_serial_connection_exchange_and_cleanup(monkeypatch):
    port = Mock()
    port.write.return_value = 3
    port.read.side_effect = [b"O", b"K", b"\n"]
    module = SimpleNamespace(serial_for_url=Mock(return_value=port), SerialException=OSError)
    monkeypatch.setitem(sys.modules, "serial", module)
    with SerialTransport("loop://") as engine:
        assert engine.exchange(b"AT\n") == b"OK\n"
        assert port.timeout == engine.timeout
    port.close.assert_called_once()


def test_serial_missing_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)
    with pytest.raises(ConfigurationError):
        SerialTransport("COM3").connect()
