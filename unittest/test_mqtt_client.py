import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from embedded_test_framework.communication.mqtt import MqttClient, make_mqtt_client


@pytest.fixture
def paho_client(monkeypatch):
    client = Mock()
    client.connect.return_value = 0
    client.loop_start.return_value = 0
    client.publish.return_value = SimpleNamespace(rc=0)
    client.reason = 0

    def loop_start():
        if client.reason is not None:
            client.on_connect(client, None, None, client.reason, None)
        return client.loop_start.return_value

    client.loop_start.side_effect = loop_start
    paho = ModuleType("paho")
    mqtt = ModuleType("paho.mqtt")
    module = ModuleType("paho.mqtt.client")
    paho.mqtt = mqtt
    mqtt.client = module
    module.CallbackAPIVersion = SimpleNamespace(VERSION2=2)
    module.Client = Mock(return_value=client)
    for name, value in (("paho", paho), ("paho.mqtt", mqtt), ("paho.mqtt.client", module)):
        monkeypatch.setitem(sys.modules, name, value)
    return client, module


def test_factory_waits_for_successful_connack_and_registers_callbacks_before_loop(paho_client):
    raw, module = paho_client
    engine = make_mqtt_client("broker", username="user", password="secret", timeout=0.1)
    assert engine.client is raw
    assert raw.connect_timeout == 0.1
    module.Client.assert_called_once_with(2, client_id="")
    raw.username_pw_set.assert_called_once_with("user", "secret")
    raw.connect.assert_called_once_with("broker", 1883)
    raw.disconnect.assert_not_called()
    engine.close()
    raw.disconnect.assert_called_once()
    raw.loop_stop.assert_called_once()


@pytest.mark.parametrize("failure", ["rejected", "no_ack", "connect", "connect_status", "loop"])
def test_factory_failures_close_client_and_network_loop(paho_client, failure):
    raw, _ = paho_client
    expected = ConnectionError
    if failure == "rejected":
        raw.reason = 5
    elif failure == "no_ack":
        raw.reason = None
        expected = TimeoutError
    elif failure == "connect":
        raw.connect.side_effect = OSError("connection failed")
        expected = OSError
    elif failure == "connect_status":
        raw.connect.return_value = 4
    else:
        raw.loop_start.return_value = 3
    with pytest.raises(expected):
        make_mqtt_client("broker", timeout=0.001)
    raw.disconnect.assert_called_once()
    raw.loop_stop.assert_called_once()


@pytest.mark.parametrize("reason_codes", [[False], [True], [False, True], []])
def test_subscribe_checks_matching_suback_even_when_callback_precedes_return(reason_codes):
    raw = Mock()
    engine = MqttClient(raw, 0.01)

    def subscribe(*args, **kwargs):
        raw.on_subscribe(raw, None, 8, [SimpleNamespace(is_failure=False)], None)
        raw.on_subscribe(raw, None, 7, [SimpleNamespace(is_failure=code) for code in reason_codes], None)
        return (0, 7)

    raw.subscribe.side_effect = subscribe
    if not reason_codes or any(reason_codes):
        with pytest.raises(ConnectionError, match="subscription rejected"):
            engine.subscribe("device/state", qos=1)
    else:
        assert engine.subscribe("device/state", qos=1) == (0, 7)
    assert engine._subacks == {}


def test_wrong_or_late_suback_does_not_confirm_next_subscription():
    raw = Mock()
    engine = MqttClient(raw, 0.001)
    raw.subscribe.return_value = (0, 7)
    with pytest.raises(TimeoutError):
        engine.subscribe("first")
    raw.on_subscribe(raw, None, 7, [SimpleNamespace(is_failure=False)], None)

    def subscribe(*args, **kwargs):
        raw.on_subscribe(raw, None, 7, [SimpleNamespace(is_failure=False)], None)
        return (0, 8)

    raw.subscribe.side_effect = subscribe
    with pytest.raises(TimeoutError):
        engine.subscribe("second")
    assert engine._subacks == {}


def test_immediate_subscribe_error_is_not_reported_as_timeout():
    raw = Mock()
    raw.subscribe.return_value = (4, None)
    with pytest.raises(ConnectionError, match="result code 4"):
        MqttClient(raw, 0.01).subscribe("topic")


def test_publish_returns_native_handle_and_reports_immediate_failure():
    raw = Mock()
    handle = Mock(rc=0)
    raw.publish.return_value = handle
    engine = MqttClient(raw, 0.01)
    assert engine.publish("topic", "payload", qos=1) is handle
    handle.wait_for_publish.assert_not_called()
    handle.rc = 4
    with pytest.raises(ConnectionError, match="publish failed"):
        engine.publish("topic", "payload")


def test_close_stops_loop_even_if_disconnect_fails():
    raw = Mock()
    raw.disconnect.side_effect = OSError("disconnect failed")
    with pytest.raises(OSError):
        MqttClient(raw, 0.01).close()
    raw.loop_stop.assert_called_once()


def test_subscribe_receives_confirmation_from_network_thread():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    raw = Mock()
    engine = MqttClient(raw, 1)
    sent = Event()

    def subscribe(*args, **kwargs):
        sent.set()
        return (0, 7)

    raw.subscribe.side_effect = subscribe
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(engine.subscribe, "device/state")
        assert sent.wait(1)
        raw.on_subscribe(raw, None, 7, [SimpleNamespace(is_failure=False)], None)
        assert pending.result(timeout=1) == (0, 7)
