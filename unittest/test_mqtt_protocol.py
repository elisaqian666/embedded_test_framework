import pytest
from embedded_test_framework.protocols.mqtt import MqttProtocol


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def publish(self, topic, payload, *, qos, retain):
        self.calls.append(("publish", topic, payload, qos, retain))
        return "published"

    def subscribe(self, topic, *, qos):
        self.calls.append(("subscribe", topic, qos))
        return "subscribed"

    def unsubscribe(self, topic):
        self.calls.append(("unsubscribe", topic))
        return "unsubscribed"


def test_mqtt_delegates_operations_with_validated_arguments() -> None:
    client = FakeClient()
    mqtt = MqttProtocol(client)

    assert mqtt.publish("device/state", b"on", qos=1, retain=True) == "published"
    assert mqtt.subscribe("device/+/state", qos=2) == "subscribed"
    assert mqtt.unsubscribe("device/#") == "unsubscribed"
    assert client.calls == [
        ("publish", "device/state", b"on", 1, True),
        ("subscribe", "device/+/state", 2),
        ("unsubscribe", "device/#"),
    ]


def test_mqtt_rejects_invalid_topics_and_qos() -> None:
    mqtt = MqttProtocol(FakeClient())

    with pytest.raises(ValueError):
        mqtt.publish("device/#", "on")
    with pytest.raises(ValueError):
        mqtt.subscribe("device/state", qos=3)
