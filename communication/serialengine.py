"""Purpose: Provide product-independent serial communication."""

import logging
import time
from contextlib import suppress

import serial

from embedded_framework.communication._text import decode_to_str_if_byte


class SerialEngine(object):
    """
    a class which enables to connect to the serial port
    """

    def __init__(self, session, port, baudrate=9600, timeout=1.0):
        self.serial_object = session
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.logger = logging.getLogger("serial")

    @staticmethod
    def __protocol__():
        """
        returns the protocol used

        :return: string
        """
        return "serial"

    def __str__(self):
        """
        returns a string representation of the object

        :return: string representation
        """
        return f"Serial engine on port: {self.port}"

    def open_serial_connection(self):
        """
        opens serial communication on default port or port provided
        """
        if not self.serial_object.isOpen():
            self.logger.debug("Openning serial connection")
            self.serial_object.port = self.port
            self.serial_object.baudrate = self.baudrate
            self.serial_object.timeout = self.timeout
            self.serial_object.xonxoff = False
            self.serial_object.rtscts = False
            self.serial_object.dsrdtr = False
            self.logger.info("opening serial connection on port: %s", self.port)
            self.serial_object.open()
            self.logger.info("serial connection established on port: %s", self.port)
            return True
        else:
            self.logger.info("serial connection already opened on port: %s", self.port)
            return False

    def check_serial_connection_open(self):
        """check_serial_connection_open: if not open open connection and read buffer"""
        self.logger.debug("checking if serial connection is open")
        connection_opened = self.open_serial_connection()
        out = None
        if connection_opened:
            self.logger.debug("reading line on serial")
            out = self.serial_object.readline()
        return out

    def write_command_on_serial(self, cmd, eol="\n"):
        """
        writes specific command for serial connection

        :param cmd: Serial command to be written
        :param eol: End of line character for the command. By default it's \n
        """
        with suppress(AttributeError):
            cmd = cmd.encode()

        with suppress(AttributeError):
            eol = eol.encode()
        self.check_serial_connection_open()
        self.logger.info("writing command on serial: %s", cmd)
        self.serial_object.write(cmd + eol)
        self.logger.debug("Command sent on serial port")

    def read_line_on_serial(self):
        """
        writes specific command for serial connection
        """
        self.check_serial_connection_open()
        out = self.serial_object.readline()
        response = decode_to_str_if_byte(out)

        while out:
            try:
                out = decode_to_str_if_byte(self.serial_object.readline())
                response += out
            except UnicodeDecodeError as e:
                self.logger.error(str(e))
                self.logger.error("Ignoring the junk output:")
                self.logger.error(out)

        self.logger.info("read line on serial: %s", response)
        return response

    def send_cmd_and_read_line_on_serial(self, cmd, wait_for=0.0):
        """
        writes specific command for serial connection

        :param cmd: Data to be sent on the serial port, can be str or bytes
        :param wait_for: Number of seconds to wait before reading the response on the serial port (float or integer)
        """
        self.write_command_on_serial(cmd)
        if wait_for:
            time.sleep(wait_for)
        return self.read_line_on_serial()

    def cancel_read(self):
        """
        Cancels a read so we can stop the reading from a different thread
        """
        self.serial_object.cancel_read()

    def read(self, size: int = 1) -> bytes:
        """Read up to size bytes without interpreting device framing or encoding."""
        self.open_serial_connection()
        return self.serial_object.read(size)

    def write(self, data: bytes) -> int:
        """Write raw bytes without appending a command terminator."""
        self.open_serial_connection()
        return self.serial_object.write(data)

    def close(self) -> None:
        """Close the serial connection."""
        self.close_serial_connection()

    def __enter__(self):
        self.open_serial_connection()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close_serial_connection(self):
        """
        closes the serial connection
        """
        self.serial_object.close()
        self.logger.info("Serial connection closed on port: %s", self.port)


def make_serial_engine(com_port, baudrate=9600, read_timeout=1.0, write_timeout=10):
    """
    make serial port

    :param com_port:
    :param baudrate:
    :param read_timeout: Timeout for reading data via serial port
    :param write_timeout: Timeout for writing data via serial port
    """
    logging.getLogger("serial").info("creating the serial engine on port: %s", com_port)
    ser = serial.Serial(timeout=read_timeout, write_timeout=write_timeout)
    return SerialEngine(ser, com_port, baudrate, read_timeout)
