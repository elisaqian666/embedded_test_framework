"""Purpose: Provide product-independent SSH and SCP communication."""

import contextlib
import logging
import math
import re
import select
import socketserver
import threading
import time
from functools import wraps

import scp
from paramiko import AuthenticationException, AutoAddPolicy, SSHClient, SSHException

from embedded_test_framework.communication._text import decode_to_str_if_byte
from embedded_test_framework.communication.base import BaseTransport
from embedded_test_framework.configurator.config_labels import LOGGERS
from embedded_test_framework.lib.basic_helper_functions import listify
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import SSHCommandError
from embedded_test_framework.lib.timeout import TimeOutError, Timer, wait_no_exception_timeout, wait_timeout

KEEP_ALIVE_INTERVAL = 2.5 * 60


def thread_lock(function):
    """Serialize shared Paramiko connection access; the RLock allows nested calls in the same thread."""

    @wraps(function)
    def locked(self, *args, **kwargs):
        with self._lock:
            return function(self, *args, **kwargs)

    return locked


class SshConnectionNotLostWithinTimeOut(TimeOutError):
    pass


class SSHNotResponsive(SSHException):
    """
    Unable to connect to client via SSH
    """

    pass


class SshTransport(BaseTransport):
    """
    An object which delivers ssh functionality preferably call the maker function to use this class wrapper for paramiko
    """

    def __init__(self, ssh_con: SSHClient, hostname, username, password, port=22, *, timeout: float = 60, retry: int = 4):
        self.ssh_con: SSHClient = ssh_con
        self.address = hostname
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.retry = retry
        self.session = None
        self._lock = threading.RLock()
        self.logger = logging.getLogger(LOGGERS.SSH_ENGINE)

    @staticmethod
    def __protocol__():
        return "ssh"

    def __str__(self):
        return f"ssh engine with parameters {self.address}, {self.username}, ********"

    @thread_lock
    def __re_init__(self):
        """
        re initializes the engine
        """
        self.logger.info("sleeping for 1 second to reinit")
        time.sleep(1)
        new_eng = make_ssh_transport(self.address, self.username, self.password, port=self.port, retry=self.retry, timeout=self.timeout)

        if self.ssh_con:  # And we still have the old SSH connection when there is issue calling "make_ssh_transport"
            try:
                self.ssh_con.close()
            except Exception:
                self.logger.exception("Error raised while closing SSH connection")

        self.ssh_con = new_eng.ssh_con
        self.username = new_eng.username
        self.password = new_eng.password
        self.port = new_eng.port
        self.session = None

    def get_ssh_connection(self):
        """returns the ssh session"""
        return self.ssh_con

    def close(self) -> None:
        """Release the SSH connection."""
        self.ssh_con.close()

    def connect(self) -> None:
        if not self.is_connected:
            self.__re_init__()

    def disconnect(self) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        return self.ssh_con is not None and self.ssh_con.get_transport() is not None and self.ssh_con.get_transport().is_active()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _ssh_exec_command_w_timeout(self, command, time_out=10):
        deadline = time.monotonic() + time_out
        channel = None
        output, errors = bytearray(), bytearray()
        try:
            _, stdout, _ = self.ssh_con.exec_command(command, timeout=time_out)
            channel = stdout.channel
            channel.shutdown_write()
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"command timed out after {time_out}s")
                received = False
                if channel.recv_ready():
                    output.extend(channel.recv(65536))
                    received = True
                if channel.recv_stderr_ready():
                    errors.extend(channel.recv_stderr(65536))
                    received = True
                if channel.exit_status_ready() and (channel.eof_received or channel.closed):
                    if not channel.recv_ready() and not channel.recv_stderr_ready():
                        status = channel.recv_exit_status()
                        if status == -1:
                            raise RuntimeError("SSH channel closed without an exit status")
                        return output.decode(errors="replace"), status, errors.decode(errors="replace")
                if not received:
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        except Exception as error:
            raise SSHCommandError(
                f"SSH command {command!r} failed (timeout={time_out}s): {error}; "
                f"stdout={output.decode(errors='replace')!r}; stderr={errors.decode(errors='replace')!r}"
            ) from error
        finally:
            if channel is not None:
                channel.close()

    def wait_for_connection_lost(self, timeout=60):
        self.logger.error("Waiting until connection is lost")
        self.pause_logging()
        start_time = time.time()
        end_time = start_time + timeout
        try:
            while time.time() < end_time:
                create_ssh_session_obj_from_hostname(
                    hostname=self.address, username=self.username, password=self.password, port=self.port, retry=1, timeout=1
                )
            self.resume_logging()
            raise SshConnectionNotLostWithinTimeOut(f"SSH connection not lost within the expected timeout of {timeout} seconds")
        except (AuthenticationException, SSHNotResponsive) as excep:
            self.resume_logging()
            self.logger.info("Expected exception caught at %f secs: %s - %s", time.time() - start_time, str(type(excep)), str(excep))
        self.logger.error("end waiting until connection is lost %f secs", time.time() - start_time)

    def wait_for_ssh_server_responsive(self, timeout=20):
        self.logger.debug(f"Waiting for SSH server to start, timeout = {timeout} seconds")
        tm = Timer(timeout)
        self.pause_logging()
        try:
            wait_no_exception_timeout(self.do_command, timeout, SSHCommandError, ":", time_out=min(10, timeout))
        finally:
            self.resume_logging()
        self.logger.debug(f"SSH server active and responsive after {tm.elapsed_time} seconds")

    def wait_for_device_detected(self, timeout=20):
        return self.wait_for_ssh_server_responsive(timeout)

    def do_ssh_command(self, command, time_out=None, rcvd_timeout=None):
        """Compatibility entry point using checked execution, never partial output.

        rcvd_timeout, when provided, caps the total timeout instead of specifying
        an idle receive window. Failure and timeout raise SSHCommandError.
        """
        if rcvd_timeout is not None:
            time_out = self.timeout if time_out is None else time_out
            for value in (time_out, rcvd_timeout):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError("SSH timeouts must be finite positive numbers")
            time_out = min(time_out, rcvd_timeout)
        return self.do_command(command, time_out=time_out)

    def exec_command(self, command: str, *, timeout: float | None = None) -> CommandResult:
        """Return output, exit code and duration; nonzero exit codes are data.

        Duration includes waiting for the shared connection lock. Transport/timeout
        failures raise SSHCommandError; callers decide whether an exit code fails a test.
        """
        time_out = self.timeout if timeout is None else timeout
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise ValueError("SSH command must be non-empty text without NUL characters")
        if isinstance(time_out, bool) or not isinstance(time_out, (int, float)) or not math.isfinite(time_out) or time_out <= 0:
            raise ValueError("SSH timeout must be a finite positive number")
        started = time.perf_counter()
        if not self._lock.acquire(timeout=time_out):
            raise SSHCommandError(f"SSH command {command!r} timed out waiting for the connection lock ({time_out}s)")
        try:
            remaining = time_out - (time.perf_counter() - started)
            if remaining <= 0:
                raise SSHCommandError(f"SSH command {command!r} timed out before execution ({time_out}s)")
            # A failed response does not prove the command did not run; never replay it.
            stdout, status, stderr = self._ssh_exec_command_w_timeout(command, remaining)
            return CommandResult(stdout, status, stderr, duration=time.perf_counter() - started)
        finally:
            self._lock.release()

    execute = exec_command
    shell = exec_command

    def do_command(self, command, time_out=None):
        """Legacy string API; new callers use execute() and inspect CommandResult."""
        return self.exec_command(command, timeout=time_out).check(SSHCommandError).stdout

    def do_command_w_exitstatus(self, command, time_out=None):
        """Legacy tuple API; nonzero status remains available to the caller."""
        result = self.exec_command(command, timeout=time_out)
        return result.stdout, result.exit_code, result.stderr

    @thread_lock
    def put_files(self, source, destination):
        """Upload once; failures never delete the target or replay a partial upload."""
        self.logger.info("putting %s to %s", source, destination)
        with scp.SCPClient(self.ssh_con.get_transport(), buff_size=16384, socket_timeout=30.0, progress=None) as scp_conn:
            scp_conn.put(source, destination, recursive=True, preserve_times=False)

    @thread_lock
    def get_files(self, remote_path, local_path):
        """
        receives files via scp
        """
        try:
            self.logger.info("getting from %s to %s", remote_path, local_path)
            with scp.SCPClient(self.ssh_con.get_transport(), buff_size=16384, socket_timeout=30.0, progress=None) as scp_conn:
                scp_conn.get(remote_path, local_path, recursive=True)
        except (OSError, AuthenticationException, SSHException, scp.SCPException) as excep:
            self.logger.error("Exception caught after opening session: %s - %s, re-initialize the engine", str(type(excep)), str(excep))
            self.__re_init__()
            self.logger.info("getting from %s to %s", remote_path, local_path)
            with scp.SCPClient(self.ssh_con.get_transport(), buff_size=16384, socket_timeout=30.0, progress=None) as scp_conn:
                scp_conn.get(remote_path, local_path, recursive=True)

    def pause_logging(self, log_it=True):
        """
        pauses paramiko and ssh engine logging => to be done when we expect outage

        :param log_it: warn whenever the logging is paused, defaults to True
        :type log_it: bool
        """
        if log_it:
            self.logger.info("Setting Paramiko and ssh logger to critical")
        self._prev_level_ssh = self.logger.level
        self.logger.setLevel(logging.CRITICAL)

    def resume_logging(self, log_it=True):
        """
        resumes logging to the state which it was before pause was called last time

        :param log_it: warn whenever the logging is paused, defaults to True
        :type log_it: bool
        """
        self.logger.setLevel(self._prev_level_ssh)
        if log_it:
            self.logger.info("Setting Paramiko and ssh logger to previous level")

    @thread_lock
    def send_command_and_wait_for_regex_in_output(self, cmd, regex, timeout=60.0, suppress=None):
        """
        sends a command and waits until a regex is found or timeout is exceeded

        :Example:

            >>> ssh_engine.send_command_and_wait_for_regex_in_output("tail -F /var/log/messages", "INFO")
            Out[2]: 'device: [INFO] service ready'
            >>> ssh_engine.send_command_and_wait_for_regex_in_output("ping 8.8.8.8", "64 bytes from 8.8.8.8")
            Out[2]: '64 bytes from 8.8.8.8: seq=0 ttl=117 time=10.494 ms'
            >>> ssh_engine.send_command_and_wait_for_regex_in_output("ping 8.8.8.8", "this does not appear")
            embedded_test_framework.lib.timeout.TimeOutError: Timeout of 60.0 seconds reached, stopping waiting for regex
            Last line read was:
            '64 bytes from 8.8.8.8: seq=59 ttl=117 time=10.696 ms'
            >>> ssh_engine.send_command_and_wait_for_regex_in_output(
            ...     "ping 8.8.8.8",
            ...     "this wil never appear",
            ...     timeout=50.0,
            ...     suppress=embedded_test_framework.lib.timeout.TimeOutError,
            ... )
            24 Feb 2021 16:54:34 ssh             ERROR    exception caught of typeTimeout of 50.0 seconds reached, stopping waiting for regex
            Last line read was:
            '64 bytes from 8.8.8.8: seq=49 ttl=117 time=10.238 ms'
            Out[2]: ''

        :param suppress: list of exceptions to suppress or a single exception
        :type suppress: list || Exception
        :param cmd: the command to start tailing the output from
        :type cmd: str
        :param regex: regex string which we will search in the logs
        :type regex: str
        :param timeout: time in seconds default: 60
        :type timeout: float
        :return: a line which matches a regex
        :rtype: str
        :raises TimeOutError: when not suppressed and no regex is found
        """
        if suppress is None:
            suppress = []
        self.logger.info("running '%s' \nwaiting until '%s' appears in output", cmd, regex)
        current_line = b""
        line_feed_bytes = ["\n".encode("utf-8"), "\r".encode("utf-8")]
        start = time.time()
        try:
            channel = self._get_interactive_shell_channel()
            channel.sendall(cmd + "\n")
        except (SSHException, TimeOutError):
            self.__re_init__()
            channel = self._get_interactive_shell_channel()
            channel.sendall(cmd + "\n")
        try:
            current_line_decoded = ""
            while True:
                self._raise_exception_when_timeout(current_line_decoded, regex, start, timeout)
                buffer = self._read_buffer_from_channel(channel)

                # Add the currently read buffer to the current line output
                current_line += buffer

                # When we reach a \n gather the line and do a regex check
                if buffer in line_feed_bytes:
                    line_decoded = decode_to_str_if_byte(current_line).rstrip("\n").rstrip("\r")
                    if line_decoded != "":
                        current_line_decoded = line_decoded
                        self.logger.debug(line_decoded)
                        if re.search(regex, current_line_decoded):
                            break
                    current_line = b""  # setting to empty byte
            channel.close()
            return current_line_decoded.rstrip("\n").rstrip("\r")
        except Exception as excep:
            self.logger.error("exception caught of type %s", excep)

            if any(isinstance(excep, exception_type) for exception_type in listify(suppress)):
                return ""
            raise

    @staticmethod
    def _read_buffer_from_channel(channel):
        if not channel.recv_ready():
            time.sleep(0.05)
            return b""
        buffer = channel.recv(1)
        # If we have an empty buffer, then the SSH session has been closed
        if len(buffer) == 0:
            raise SSHException("Connection was closed during tailing and waiting for regex")
        return buffer

    def _get_interactive_shell_channel(self):
        tty_width = 4096  # high number
        tty_height = 100
        channel = self.ssh_con.invoke_shell(width=tty_width, height=tty_height)
        num_of_seconds_we_can_go_without_a_print_to_console = 10.0
        channel.settimeout(num_of_seconds_we_can_go_without_a_print_to_console)
        wait_timeout(channel.send_ready, timeout_param=10)
        return channel

    @staticmethod
    def _raise_exception_when_timeout(current_line_decoded, regex, start, timeout):
        if time.time() > start + timeout:
            raise TimeOutError(
                f"Timeout of {timeout} seconds reached, stopping waiting for regex '{regex}'\nLast line read was:\n'{current_line_decoded}'"
            )


class SSHForwardServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class SSHForwardRequestHandler(socketserver.BaseRequestHandler):
    logger = logging.getLogger("ssh")
    BUFFER_SIZE = 1024

    def setup(self):
        super().setup()
        self.channel = self._get_ssh_channel()

    def handle(self):
        while True:
            read_list, *_ = select.select([self.request, self.channel], [], [])

            if not read_list:
                self.logger.debug("No data received while SSH tunnel forwarding, closing tunnel.")
                break

            if self.request in read_list:
                try:
                    data = self.request.recv(self.BUFFER_SIZE)
                    if len(data) == 0:
                        break
                    self.channel.send(data)
                except OSError:
                    break

            if self.channel in read_list:
                try:
                    data = self.channel.recv(self.BUFFER_SIZE)
                    if len(data) == 0:
                        break
                    self.request.send(data)
                except OSError:
                    break

        with contextlib.suppress(Exception):
            self.channel.close()
            self.request.close()

    def _get_ssh_channel(self):
        channel = self.ssh_transport.open_channel("direct-tcpip", (self.dest_address, self.dest_port), self.request.getpeername())

        self.logger.debug(
            "SSH tunnel opened successfully %r -> %r -> %r",
            self.request.getpeername(),
            channel.getpeername(),
            (self.dest_address, self.dest_port),
        )

        return channel


class SSHTunnelForwarder:
    """
    SSH Tunnel Forwarder to forward traffic from a local port to a remote address and port over SSH.
    It's inspired by https://github.com/paramiko/paramiko/blob/main/demos/forward.py
    """

    logger = logging.getLogger("ssh")

    def __init__(self, local_port, remote_address, remote_port, ssh_transport):
        self.local_port = local_port
        self.remote_address = remote_address
        self.remote_port = remote_port
        self.ssh_transport = ssh_transport
        self._server = SSHForwardServer(("", self.local_port), self._get_request_handler())
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _get_request_handler(self):
        # RequestHandler only accepts custom variables to be class attributes and then pass that class to initiate SSHForwardServer
        SSHForwardRequestHandler.dest_address = self.remote_address
        SSHForwardRequestHandler.dest_port = self.remote_port
        SSHForwardRequestHandler.ssh_transport = self.ssh_transport

        return SSHForwardRequestHandler

    def start(self):
        if self._server_thread.is_alive():
            self.logger.info("SSH tunnel forwarder on port %d is already running.", self.local_port)
            return

        self.logger.info("Starting SSH tunnel forwarder on port %d", self.local_port)

        self._server_thread.start()

        self.logger.info("SSH tunnel forwarder on port %d has been started successfully.", self.local_port)

    def stop(self):
        self.logger.info("Stopping SSH tunnel forwarder on port %d", self.local_port)

        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            self.logger.error("Error stopping tunnel forwarder.", exc_info=True)
            return

        self.logger.info("SSH tunnel forwarder on port %d has been stopped successfully.", self.local_port)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def create_ssh_session_obj_from_hostname(hostname, username, password, port=22, retry=4, timeout=10):
    """
    initiates the ssh_con property

    :param timeout: allows to fine-tune timeout on connect call
    :param retry: the number of times will be tried in case of failure
    :param port: the port => defaults to 22
    :param hostname: the hostname of the device you want to connect to
    :param username: the username of the user to log in to via ssh (THIS CAN'T BE EMPTY)
    :param password: the password for the username (if empty set empty string)
    :return: a transport (paramiko)
    :raises: AuthenticationException
    :raises: SSHNotResponsive
    """
    ssh_con = None
    if type(port) is str and port.isdigit():
        port = int(port)

    for cur_round in range(retry + 1):
        ssh_con = SSHClient()
        try:
            logging.getLogger("ssh").info("creating ssh session %s %s %s:%s", username, _hide_password(password), hostname, str(port))

            ssh_con.set_missing_host_key_policy(AutoAddPolicy)
            ssh_con.connect(
                hostname,
                port,
                username=username,
                password=password,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=200,
            )
            return ssh_con
        except AuthenticationException:
            with contextlib.suppress(Exception):
                ssh_con.close()  # Transport is created at beginning of "connect" method, so we need to close it
            raise
        except Exception as excep:
            with contextlib.suppress(Exception):
                ssh_con.close()  # Transport is created at beginning of "connect" method, so we need to close it
            logging.getLogger("ssh").debug("Traceback", exc_info=True)
            logging.getLogger("ssh").error(
                "caught %s: %s While connecting to %s on port %d with %s\nRetried %s time",
                type(excep),
                str(excep),
                hostname,
                port,
                username,
                str(cur_round),
            )
            time.sleep(1)

    raise SSHNotResponsive(f"While connecting to {hostname} on port {port} with {username}")


def _hide_password(_password):
    return "********"


def make_ssh_transport(address: str, username: str, password: str, port: int = 22, retry: int = 4, timeout: float = 10) -> SshTransport:
    """Connect using caller-provided credentials; no device-model lookup.

    :param address: Device hostname or IP address.
    :param username: SSH login name.
    :param password: SSH login password.
    :param port: SSH server port.
    :param retry: Additional connection attempts, following the existing engine.
    :param timeout: Default command budget and timeout per connection attempt, in seconds.
    :returns: Connected SSH engine.
    """
    connection = create_ssh_session_obj_from_hostname(address, username, password, port, retry, timeout)
    return SshTransport(connection, address, username, password, port, timeout=timeout, retry=retry)
