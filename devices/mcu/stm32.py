from typing import Any

from embedded_test_framework.devices.base import BaseDevice, Capability
from embedded_test_framework.protocols.can import CanProtocol
from embedded_test_framework.protocols.mqtt import MqttProtocol


class Stm32Device(BaseDevice):
    """STM32 adapter exposing its configured serial transport."""

    connection_capabilities = {
        Capability.SERIAL: frozenset({"serial"}),
        Capability.MQTT: frozenset({"mqtt"}),
        Capability.CAN: frozenset({"can"}),
    }

    def can(self, connection: str | None = None) -> CanProtocol:
        return CanProtocol(self.engine(connection, protocol="can"))

    def serial(self, connection: str | None = None) -> Any:
        return self.engine(connection, protocol="serial")

    def mqtt(self, connection: str | None = None) -> MqttProtocol:
        return MqttProtocol(self.engine(connection, protocol="mqtt"))
