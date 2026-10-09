"""Small, client-library-agnostic MQTT protocol facade."""

from typing import Any


class MqttProtocol:
    """Publish and subscribe through an injected MQTT client."""

    def __init__(self, client: Any) -> None:
        if not all(callable(getattr(client, method, None)) for method in ("publish", "subscribe", "unsubscribe")):
            raise TypeError("MQTT requires a client with publish, subscribe, and unsubscribe methods")
        self.client = client

    @staticmethod
    def _topic(topic: str, *, allow_wildcards: bool) -> str:
        if not isinstance(topic, str) or not topic or (not allow_wildcards and ("+" in topic or "#" in topic)):
            raise ValueError("MQTT topic must be non-empty" + (" and cannot contain wildcards" if not allow_wildcards else ""))
        return topic

    @staticmethod
    def _qos(qos: int) -> int:
        if type(qos) is not int or not 0 <= qos <= 2:
            raise ValueError("MQTT QoS must be 0, 1, or 2")
        return qos

    def publish(self, topic: str, payload: str | bytes | None = None, *, qos: int = 0, retain: bool = False) -> Any:
        if type(retain) is not bool:
            raise TypeError("MQTT retain must be a bool")
        return self.client.publish(self._topic(topic, allow_wildcards=False), payload, qos=self._qos(qos), retain=retain)

    def subscribe(self, topic: str, *, qos: int = 0) -> Any:
        return self.client.subscribe(self._topic(topic, allow_wildcards=True), qos=self._qos(qos))

    def unsubscribe(self, topic: str) -> Any:
        return self.client.unsubscribe(self._topic(topic, allow_wildcards=True))

    def receive(self, timeout: float = 10) -> tuple[str, bytes]:
        receive = getattr(self.client, "receive", None)
        if not callable(receive):
            raise TypeError("MQTT client does not support receiving messages")
        return receive(timeout)
