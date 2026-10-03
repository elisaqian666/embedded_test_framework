from typing import Any

from embedded_test_framework.devices.base import BaseDevice, Capability
from embedded_test_framework.protocols.mqtt import MqttProtocol


class Stm32Device(BaseDevice):
    """STM32 adapter exposing its configured serial transport."""

    capabilities = frozenset({Capability.SERIAL})
    connection_capabilities = {Capability.MQTT: frozenset({"mqtt"})}

    def serial(self, connection: str | None = None) -> Any:
        self.require(Capability.SERIAL)
        return self.engine(connection)

    def mqtt(self, connection: str = "mqtt") -> MqttProtocol:
        self.require(Capability.MQTT)
        return MqttProtocol(self.engine(connection))
