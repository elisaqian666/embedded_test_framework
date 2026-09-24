"""Purpose: Provide product-independent TCP and UDP communication."""

import logging
import socket
import struct

from embedded_framework.communication.base import BaseTransport

CRLF = "\r\n"


class SocketTransport(BaseTransport):
    """Client support class for simple Internet protocols."""

    def __init__(self, host, port):
        """
        Connect to an Internet server.

        :param host: host address
        :param port: port to connect to
        """
        self.host = host
        self.port = port
        self.sock = None
        self.file = None
        self.last_line = ""
        self.logger = logging.getLogger("socket")
        self.socket_parameters = (socket.AF_INET, socket.SOCK_STREAM, 0, 5)

    def __del__(self):
        """close the socket"""
        if self.sock:
            self.close()

    def __re_init__(self):
        """
        re initializes the engine
        """
        had_file = self.file is not None
        self.close()
        replacement = make_socket_transport(self.host, self.port, *self.socket_parameters)
        self.sock = replacement.sock
        replacement.sock = None
        if had_file:
            self.associate_file()

    def writeline(self, line):
        """
        Send a line to the server.

        :param line: line to send
        """
        self.logger.debug("write data (%s) from socket (host=%s,port=%d)" % (line, self.host, self.port))
        data_to_write = line + CRLF
        self.sock.sendall(data_to_write.encode("utf-8"))  # unbuffered write
        self.last_line = line

    def send(self, data: bytes) -> None:
        """Send raw bytes without adding framing or text encoding."""
        self.sock.sendall(data)

    def receive(self, size: int = 4096) -> bytes:
        """Receive up to size bytes; an empty result means peer EOF on TCP."""
        return self.sock.recv(size)

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def receive_buffer(self, size):
        """
        receive data from socket

        :param size: max size of data to receive
        :return: received data
        """
        self.logger.debug("receive buffer size (%d) from socket (host=%s,port=%d)" % (size, self.host, self.port))
        received_data = self.sock.recv(size)
        return received_data.decode("utf-8")

    def read(self, maxbytes=None):
        """
        Read data from server.

        :param maxbytes: line to send
        :return: all file buffer read or maxbytes size from buffer
        """
        self.logger.debug("read data from socket (host=%s,port=%d)" % (self.host, self.port))
        data = self.file.read() if maxbytes is None else self.file.read(maxbytes)
        return data.decode("utf-8")

    def readline(self):
        """
        Read a line from the server.  Strip trailing CR and/or LF.

        :return: line read from server
        """
        self.logger.info("read line from server")
        s = self.file.readline()
        if not s:
            raise EOFError
        s = s.decode("utf-8")
        s = s.rstrip("\r\n")
        self.logger.error(s)
        return s

    def open(self):
        """open the socket"""
        self.sock.connect((self.host, self.port))
        self.logger.info("socket opened (host=%s,port=%d)" % (self.host, self.port))

    def connect(self) -> None:
        if self.sock is None:
            self.sock = socket.socket(*self.socket_parameters[:3])
            self.set_socket_timeout(self.socket_parameters[3])
            self.open()

    def disconnect(self) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        return self.sock is not None

    def close(self):
        """close the socket"""
        if self.file is not None:
            self.file.close()
            self.file = None
        if self.sock:
            self.sock.close()
            self.sock = None
        self.logger.info("socket closed (host=%s,port=%d)" % (self.host, self.port))

    def associate_file(self):
        """associate file"""
        self.file = self.sock.makefile("rb")  # buffered
        self.logger.info("socket file associated (host=%s,port=%d)" % (self.host, self.port))

    def set_socket_option(self, level, optname, value):
        """
        Sets a socket option.
        This method allows you to configure various options for the socket at the specified level.
        Options can be related to general socket behavior, transport-layer options, or protocol-specific settings.

        :param level: The level at which the option resides. This is usually one of the socket module constants
                      such as `socket.SOL_SOCKET` for socket-level options, or `socket.IPPROTO_TCP` for TCP-level
                      options.
        :param optname: The option name to be set. This is typically one of the socket module constants such as
                        `socket.SO_REUSEADDR` for reusing local addresses or `socket.TCP_NODELAY` for disabling
                        Nagle's algorithm
        :param value: The value to set for the specified option. The type and format of this value depend on the
                      option being set. For instance, it could be an integer, a binary string, or another type
                      depending on the option.
        """
        self.sock.setsockopt(level, optname, value)
        self.logger.info("Set socket option (level=%d, optname=%d, value=%s)" % (level, optname, value))

    def bind_socket(self, host, port):
        """Binds socket with specific network address and port number."""
        self.sock.bind((host, port))
        self.logger.info(f"Bind socket to {self.host}:{self.port}")

    def receive_data(self, buffer_size):
        """
        Receive data from the socket.

        :param buffer_size: The maximum amount of data to receive
        :return: A tuple (data, address) where data is the received data and address is the sender's address
        """
        self.logger.info(f"Receiving data with buffer size {buffer_size} from socket (host={self.host}, port={self.port})")
        data, address = self.sock.recvfrom(buffer_size)
        self.logger.debug("Received data from %s: %r", address, data)
        return data, address

    def send_data_to_dest(self, msg, dst):
        """
        This method is used to send data to a specific address.
        It is commonly used with a UDP (User Datagram Protocol) socket.

        :param msg: The data to be sent. It must be in bytes format, so it's converted before being sent
        :param dst: A tuple containing the IP address and port number of the destination (e.g., ("127.0.0.1", 12345)).
        """
        self.logger.info(f"Sending message: {msg} to destination: {dst}")
        if isinstance(msg, bytes):
            payload = msg
        elif isinstance(msg, str):
            payload = msg.encode("utf-8")
        else:
            payload = "\r\n".join(msg).encode("utf-8")
        self.sock.sendto(payload, dst)

    def set_socket_timeout(self, timeout):
        """
        Sets a timeout on socket operations.
        This method controls how long the socket will wait for a blocking
        operation to complete before raising an exception if it times out.

        :param timeout: The timeout to be set - in seconds
        """
        self.logger.info(f"Setting a timeout of {timeout} seconds.")
        self.sock.settimeout(timeout)
        self.socket_parameters = (*self.socket_parameters[:3], timeout)

    def convert_ip_address_to_byte_format(self, ip_address):
        """
        Converts the dotted-decimal IP address into its binary format.
        The result is a 4-byte string that represents the IP address in network byte order.

        :param ip_address: IPv4 Address to be converted
        :return: It returns a 4-byte binary string that represents the IPv4 address in network byte order.
        """
        self.logger.info(f"Converting {ip_address} to 4-byte format.")
        return socket.inet_aton(ip_address)

    def join_multicast_group(self, multicast_group):
        """
        Join a multicast group on all interfaces.

        :param multicast_group: IP address of the multicast group
        """
        mreq = struct.pack("=4s4s", socket.inet_aton(multicast_group), socket.inet_aton("0.0.0.0"))
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.logger.info(f"Joined multicast group {multicast_group}")


def make_socket_transport(host, port, family=socket.AF_INET, s_type=socket.SOCK_STREAM, proto=0, s_timeout=5):
    """
    delivers a socket engine object

    :param host: the device to communicate with
    :param port: the port to connect to
    :param family: the address family (e.g., socket.AF_INET)
    :param s_type: the socket type (e.g., socket.SOCK_STREAM)
    :param proto: the protocol (e.g., socket.IPPROTO_TCP)
    :param s_timeout: timeout for opening the socket, in seconds
    :return: a socket engine object
    """
    client = SocketTransport(host, port)
    client.socket_parameters = (family, s_type, proto, s_timeout)
    # create the socket here simplifies unitest
    client.sock = socket.socket(family, s_type, proto)
    client.set_socket_timeout(s_timeout)
    try:
        client.open()
    except OSError:
        client.close()
        raise
    return client


