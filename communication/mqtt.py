"""MQTT communication backed by paho-mqtt."""

from queue import Empty, Queue
from threading import Event
from typing import Any


class MqttClient:
    """Connected MQTT client with subscription confirmation and a message queue."""

    def __init__(self, client: Any, timeout: float) -> None:
        self.client, self.timeout = client, timeout
        self.messages: Queue[tuple[str, bytes]] = Queue()
        self.subscribed = Event()
        self.client.on_message = lambda _client, _userdata, message: self.messages.put((message.topic, message.payload))
        self.client.on_subscribe = lambda *_args: self.subscribed.set()

    def publish(self, *args: Any, **kwargs: Any) -> Any:
        return self.client.publish(*args, **kwargs)

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        self.subscribed.clear()
        result = self.client.subscribe(*args, **kwargs)
        if not self.subscribed.wait(self.timeout):
            raise TimeoutError("Timed out subscribing to MQTT topic")
        return result

    def unsubscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self.client.unsubscribe(*args, **kwargs)

    def receive(self, timeout: float) -> tuple[str, bytes]:
        try:
            return self.messages.get(timeout=timeout)
        except Empty as error:
            raise TimeoutError("Timed out waiting for MQTT message") from error

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def __enter__(self) -> "MqttClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def make_mqtt_client(host: str, port: int = 1883, client_id: str = "", username: str | None = None, password: str | None = None, timeout: float = 10) -> MqttClient:
    """Connect a paho MQTT client and start its network loop."""
    try:
        import paho.mqtt.client as paho
    except ImportError as error:
        raise ImportError("paho-mqtt is required for MQTT connections") from error
    client = paho.Client(client_id=client_id)
    if username is not None:
        client.username_pw_set(username, password)
    client.connect(host, port, keepalive=int(timeout))
    client.loop_start()
    return MqttClient(client, timeout)
