"""MQTT communication backed by paho-mqtt."""

import math
import time
from queue import Empty, Queue
from threading import Condition, Event, Lock
from typing import Any


class MqttClient:
    """MQTT client with confirmed subscriptions and asynchronous publish handles."""

    def __init__(self, client: Any, timeout: float) -> None:
        self.client, self.timeout = client, timeout
        self.messages: Queue[tuple[str, bytes]] = Queue()
        self._connected = Event()
        self._connection_reason = None
        self._subscribe_lock = Lock()
        self._suback_condition = Condition()
        self._subscribing = False
        self._subacks: dict[int, Any] = {}
        self.client.on_connect = self._on_connect
        self.client.on_message = lambda _client, _userdata, message: self.messages.put((message.topic, message.payload))
        self.client.on_subscribe = self._on_subscribe

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties) -> None:
        self._connection_reason = reason_code
        self._connected.set()

    def _on_subscribe(self, _client, _userdata, mid, reason_codes, _properties) -> None:
        with self._suback_condition:
            if self._subscribing:
                self._subacks[mid] = reason_codes
                self._suback_condition.notify_all()

    def publish(self, *args: Any, **kwargs: Any) -> Any:
        """Return Paho's handle; call wait_for_publish() to wait for completion."""
        result = self.client.publish(*args, **kwargs)
        if result.rc != 0:
            raise ConnectionError(f"MQTT publish failed with result code {result.rc}")
        return result

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        with self._subscribe_lock, self._suback_condition:
            self._subscribing = True
            try:
                result = self.client.subscribe(*args, **kwargs)
                status, mid = result
                if status != 0:
                    raise ConnectionError(f"MQTT subscribe failed with result code {status}")
                if not self._suback_condition.wait_for(lambda: mid in self._subacks, timeout=self.timeout):
                    raise TimeoutError(f"Timed out subscribing to MQTT topic (mid={mid})")
                reason_codes = self._subacks[mid]
                if not reason_codes or any(code.is_failure for code in reason_codes):
                    raise ConnectionError(f"MQTT subscription rejected (mid={mid}): {reason_codes}")
                return result
            finally:
                self._subscribing = False
                self._subacks.clear()

    def unsubscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self.client.unsubscribe(*args, **kwargs)

    def receive(self, timeout: float) -> tuple[str, bytes]:
        try:
            return self.messages.get(timeout=timeout)
        except Empty as error:
            raise TimeoutError("Timed out waiting for MQTT message") from error

    def close(self) -> None:
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def __enter__(self) -> "MqttClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def make_mqtt_client(
    host: str, port: int = 1883, client_id: str = "", username: str | None = None, password: str | None = None, timeout: float = 10
) -> MqttClient:
    """Return a client only after a successful MQTT connection acknowledgement."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("MQTT timeout must be a finite positive number")
    try:
        import paho.mqtt.client as paho
    except ImportError as error:
        raise ImportError("paho-mqtt is required for MQTT connections") from error
    client = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=client_id)
    engine = MqttClient(client, timeout)
    client.connect_timeout = timeout
    if username is not None:
        client.username_pw_set(username, password)
    deadline = time.monotonic() + timeout
    try:
        status = client.connect(host, port)
        if status != 0:
            raise ConnectionError(f"MQTT connect failed with result code {status}")
        status = client.loop_start()
        if status != 0:
            raise ConnectionError(f"MQTT network loop failed with result code {status}")
        if not engine._connected.wait(max(0, deadline - time.monotonic())):
            raise TimeoutError("Timed out waiting for MQTT connection acknowledgement")
        if engine._connection_reason != 0:
            raise ConnectionError(f"MQTT connection rejected: {engine._connection_reason}")
    except BaseException as error:
        try:
            engine.close()
        except Exception as cleanup_error:
            error.add_note(f"MQTT cleanup also failed: {cleanup_error}")
        raise
    return engine
