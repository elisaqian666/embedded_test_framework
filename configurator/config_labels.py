import enum
import os
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path


class MetaConst(type):
    __test__ = None

class Const(object, metaclass=MetaConst):
    """Base class for constant enumerations."""

    def __setattr__(self, name, value):
        raise TypeError("Cannot rebind constant (%s)" % name)

    def __getattr__(self, name):
        return self[name]


class ENGINES(Const):

    ADB = "adb"
    APPIUM = "appium"
    UIAUTOMATOR2 = "uiautomator2"
    BLE = "ble"
    REST = "rest"
    HTTP = "http"
    HTTPS = "https"
    HTTP_AGNOSTIC = "http_agnostic"
    MONITORING_UART = "monitoring_uart_serial"
    SSH = "ssh"
    SERIAL = "serial"
    SOCKET = "socket"
    TCP = "tcp"
    UDP = "udp"
    WEBSOCKET = "websocket"
    FTP = "ftp"
    FTPS = "ftps"
    SFTP = "sftp"

class LOGLEVELS(Const):

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class PORTS(Const):

    SSH = 22
    REST = 80
    HTTPS = 443
    ADB_DAEMON = 5555
    FTPPORT21 = 21
    SFTPPORT = 22
    SFTPPORT_FTP_MIRROR = 2022
    QEMU_SSH = 2200
    REST = 4003

class LOGGERS(Const):

    ADB = "adb"
    APPIUM = "appium"
    CONFIG = "config"
    FEATURE = "feature"
    HELPER = "helper"
    HTTP = "http"
    HTTPS = "https"
    MASTER = "master"
    PARAMIKO = "paramiko"
    REST = "rest"
    SERIAL = "serial"
    TEST_CASE = "test_case"
    WEBSOCKET = "websocket"
    SLAVE = "slave"
    MASTER_SLAVE = "master_slave"
    SETUP = "setup"
    SSH_ENGINE = "ssh_engine"
    FTP_ENGINE = "ftp_engine"
    HTTP_ENGINE = "http_engine"
    SERIAL_ENGINE = "serial_engine"
    SOCKET_ENGINE = "socket_engine"
    WEBSOCKET_ENGINE = "websocket_engine"
    
