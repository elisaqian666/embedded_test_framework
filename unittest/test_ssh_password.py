import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from embedded_test_framework.engine import SSHTransport
from embedded_test_framework import TransportError


def test_password_session_executes_and_closes(monkeypatch):
    client, channel = Mock(), Mock()
    client.get_transport.return_value.open_session.return_value = channel
    channel.recv_ready.side_effect = [True, False]
    channel.recv_stderr_ready.return_value = False
    channel.exit_status_ready.return_value = True
    channel.recv.return_value = b"6.6.1\n"
    channel.recv_exit_status.return_value = 0
    monkeypatch.setitem(sys.modules, "paramiko", SimpleNamespace(SSHClient=lambda: client, RejectPolicy=Mock()))
    with SSHTransport("192.168.1.103", password="test-secret") as engine:
        result = engine.execute("uname -r")
        assert result.ok and result.stdout == "6.6.1\n"
        channel.exec_command.assert_called_once_with("uname -r")
        assert client.connect.call_args.kwargs["password"] == "test-secret"
    channel.close.assert_called_once()
    client.close.assert_called_once()
    assert not engine.connected


def test_password_failure_does_not_fall_back(monkeypatch):
    client = Mock()
    client.connect.side_effect = RuntimeError("authentication failed")
    monkeypatch.setitem(sys.modules, "paramiko", SimpleNamespace(SSHClient=lambda: client, RejectPolicy=Mock()))
    engine = SSHTransport("192.168.1.103", password="test-secret")
    engine._run = Mock()
    with pytest.raises(TransportError):
        engine.connect()
    client.close.assert_called_once()
    engine._run.assert_not_called()
    assert not engine.connected
