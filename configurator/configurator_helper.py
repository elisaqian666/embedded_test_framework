"""Store generic configuration data for embedded devices, including logging and connection settings."""
import enum
import time
from collections import namedtuple
from dataclasses import dataclass
from importlib.resources import files
from os import getenv, path
from platform import system
from typing import Annotated, NamedTuple
from embedded_framework.configurator.config_labels import ENGINES, LOGLEVELS, PORTS

@enum.unique
class UartSerialConfig:
    port: str
    baudrate: int
    timeout: int
    monitored_device: str

class DeviceUnderTest(NamedTuple):
    """Named tuple for DUT configuration."""

    hostname: str
    model_name: str
    virtual: bool = False
    port_dictionary: dict = {
        ENGINES.SSH: PORTS.SSH,
        ENGINES.REST: PORTS.REST,
        ENGINES.ADB: PORTS.ADB_DAEMON,
    }
    mac_address: str
    serial_number: int
    default_configuration: dict | None = None
    usb_serial_number: str | None = None
    adb_key_auth: bool | None = False
    uart_serial_config: UartSerialConfig | None = None

class OTATimeouts(enum.Enum):
    """Timeouts for OTA operations."""

    WAIT_FOR_START: 60
    WAIT_FOR_DOWNLOAD: 30
    WAIT_FOR_INSTALL: 150
    WAIT_FOR_SUCCESS: 30
    WAIT_FOR_REBOOT: 20
    WAIT_FOR_READY: 100
    DOWNLOADING: 300
    INSTALLING: 600

