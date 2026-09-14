import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import pytest

from embedded_test_framework import Device, Registry, load_device, ConfigurationError, TransportError, CapabilityError, CleanupError
from embedded_test_framework.dut.services import SystemService, HealthService
from embedded_test_framework.engine import MemoryTransport, HttpTransport, SSHTransport, CommandResult, SerialTransport


def test_device_service_lifecycle():
    transport = MemoryTransport({"version": "1.0"})
    device = Device("dut", {"shell": transport})
    with pytest.raises(TransportError):
        device.execute("version")
    with device:
        assert SystemService(device).version("version") == "1.0"
        with pytest.raises(CapabilityError):
            device.request("GET", "/")
        with pytest.raises(CapabilityError):
            device.request("GET", "/", channel="shell")
        with pytest.raises(TransportError):
            device.execute("unregistered")
    assert not device.connected and not transport.connected


def test_failed_connection_rolls_back_in_reverse_order():
    events = []
    class Tracking(MemoryTransport):
        def __init__(self, name):
            super().__init__()
            self.name = name
        def connect(self):
            events.append("open " + self.name)
            if self.name == "b":
                raise TransportError("offline")
            return super().connect()
        def close(self):
            events.append("close " + self.name)
            super().close()
    device = Device("dut", {name: Tracking(name) for name in "abc"})
    with pytest.raises(TransportError):
        device.connect()
    assert events == ["open a", "open b", "close b", "close a"]
    assert not device.connected


def test_cleanup_attempts_all_and_preserves_body_exception():
    a, b = MemoryTransport(), MemoryTransport()
    a.close = Mock(side_effect=RuntimeError("close error"))
    b.close = Mock(side_effect=RuntimeError("close error"))
    device = Device("dut", {"a": a, "b": b})
    with pytest.raises(CleanupError) as caught:
        device.close()
    assert len(caught.value.errors) == 2
    with pytest.raises(ValueError, match="body") as caught:
        with device:
            raise ValueError("body")
    assert caught.value.__notes__
    assert a.close.call_count == b.close.call_count == 2


def test_config_environment_and_custom_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_VERSION", "2.0")
    registry = Registry.defaults()
    registry.register_transport("vendor", MemoryTransport)
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"devices": {"dut": {"channels": {
        "shell": {"type": "vendor", "responses": {"version": "${TEST_VERSION}"}}
    }}}}), encoding="utf-8")
    with load_device(path, registry=registry) as dut:
        assert dut.execute("version").stdout == "2.0"
    monkeypatch.delenv("TEST_VERSION")
    with pytest.raises(ConfigurationError):
        load_device(path, registry=registry)
    with pytest.raises(ConfigurationError):
        registry.register_transport("vendor", MemoryTransport)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, "5"])
def test_invalid_timeout(timeout):
    with pytest.raises(ConfigurationError):
        MemoryTransport(timeout=timeout)


def test_http_real_local_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status = 503 if self.path == "/bad" else 200
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps({"path": self.path}).encode())
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(201)
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with Device("dut", {"api": HttpTransport(f"http://127.0.0.1:{server.server_port}")}) as dut:
            assert HealthService(dut).check()
            assert not HealthService(dut, path="/bad").check()
            assert dut.request("GET", "/q", params={"x": [1, 2]}).json()["path"] == "/q?x=1&x=2"
            assert dut.request("POST", "/", payload={"value": False}).json() == {"value": False}
            with pytest.raises(ConfigurationError):
                dut.request("GET", "https://other.example/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_ssh_failure_does_not_mark_connected():
    transport = SSHTransport("example.test")
    with patch.object(transport, "_run", return_value=CommandResult("true", exit_code=255)):
        with pytest.raises(TransportError):
            transport.connect()
    assert not transport.connected


def test_serial_partial_reply_is_timeout():
    from embedded_test_framework import OperationTimeout
    transport = SerialTransport("unused", timeout=0.001)
    transport._serial = Mock()
    transport._serial.write.return_value = 1
    transport._serial.read.return_value = b"x"
    transport.connected = True
    with pytest.raises(OperationTimeout):
        transport.exchange(b"a")
    assert transport._serial.timeout == transport.timeout
