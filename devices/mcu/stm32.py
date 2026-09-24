from typing import Any

from embedded_framework.devices.base import BaseDevice, Capability


class Stm32Device(BaseDevice):
    """STM32 adapter exposing its configured serial transport."""

    capabilities = frozenset({Capability.SERIAL})

    def serial(self, connection: str | None = None) -> Any:
        self.require(Capability.SERIAL)
        return self.engine(connection)
