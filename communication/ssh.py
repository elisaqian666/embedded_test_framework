"""Purpose: Provide product-independent SSH and SCP communication."""

import contextlib
import logging
import re
import select
import socketserver
import threading
import time
from functools import wraps

import gevent
import scp
from paramiko import AuthenticationException, AutoAddPolicy, SSHClient, SSHException
from embedded_framework.configurator.config_labels import LOGGERS
from embedded_framework.communication._text import decode_to_str_if_byte
from embedded_framework.communication.base import BaseTransport
from embedded_framework.lib.basic_helper_functions import listify
from embedded_framework.lib.custom_exception import EmbeddedFrameworkException
from embedded_framework.lib.timeout import TimeOutError, Timer, wait_no_exception_timeout, wait_timeout

KEEP_ALIVE_INTERVAL = 2.5 * 60
CHANNEL_TIME_OUT = 60


def thread_lock(function):
    """Serialize shared Paramiko connection access; the RLock allows nested calls in the same thread."""

    @wraps(function)
    def locked(self, *args, **kwargs):
        with self._lock:
            return function(self, *args, **kwargs)

    return locked


class SshConnectionNotLostWithinTimeOut(TimeOutError):
    pass


class EofNotReceivedError(RuntimeError):
    pass


class SSHNotResponsive(SSHException):
    """
    Unable to connect to client via SSH
    """

    pass


class SSHCommandFailed(SSHException):
    """
    Fail to execute command vis SSH
    """

    pass


class SshTransport(BaseTransport):
    """
    An object which delivers ssh functionality preferably call the maker function to use this class wrapper for paramiko
    """

    def __init__(self, ssh_con: SSHClient, hostname, username, password, port=22):
        self.ssh_con: SSHClient = ssh_con
        self.address = hostname
        self.username = username
        self.password = password
        self.port = port
        self.session = None
        self._lock = threading.RLock()
        self.logger = logging.getLogger(LOGGERS.HELPER)

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
        new_eng = make_ssh_transport(self.address, self.username, self.password, port=self.port)

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
        try:
            start_time = time.time()
            _, stdout, stderr = self.ssh_con.exec_command(command, timeout=time_out)
            self.logger.debug("Run exec_command finished.")
            end_time = start_time + (max(time_out, CHANNEL_TIME_OUT) if time_out else CHANNEL_TIME_OUT)

            if not stdout.channel.exit_status_ready():
                self.logger.debug("Waiting for exit status ready...")
                while time.time() < end_time:
                    if stdout.channel.exit_status_ready():
                        break
                    time.sleep(0.05)
                else:
                    # This is safe workaround from https://github.com/paramiko/paramiko/issues/109#issuecomment-111621658
                    self.logger.error("No EOF received. Force closing before trying reading data")
                    stdout.channel.close()  # Force closing it so that we won't hang on read()
                    stderr.channel.close()  # Force closing it so that we won't hang on read()

                    cur_stdout = None
                    with contextlib.suppress(Exception):
                        cur_stdout = str(stdout.read().decode())
                    cur_stderr = None
                    with contextlib.suppress(Exception):
                        cur_stderr = str(stderr.read().decode())

                    error_message = "\n".join(
                        [
                            f"{self.__str__()}: '{command}' executed but timed out waiting stdout channel exit ({stdout.channel.closed=}, {stdout.channel.status_event=}, {stdout.channel.exit_status=}) for ({CHANNEL_TIME_OUT} sec)",
                            "Current stdout " + "=" * 30,
                            str(cur_stdout),
                            "Current stderr " + "=" * 30,
                            str(cur_stderr),
                        ]
                    )
                    raise EofNotReceivedError(error_message)
            self.logger.debug(
                "time spent=%f stdout_eof=%d, stderr_eof=%d",
                time.time() - start_time,
                stdout.channel.eof_received,
                stderr.channel.eof_received,
            )
            process_exit_status = stdout.channel.recv_exit_status()
            ret_stdout = str(stdout.read().decode())
            ret_stderr = str(stderr.read().decode())
            return_val = ret_stdout, process_exit_status, ret_stderr
            self.logger.debug("stdout_read:\t%s" % ret_stdout)
            self.logger.debug("process exit status:\t%d" % process_exit_status)
            self.logger.debug("stderr_read:\t%s" % ret_stderr)
            return return_val
        except Exception as e:
            raise SSHCommandFailed(f"{self.__str__()}: {command=} and {time_out=}") from e

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
        wait_no_exception_timeout(self.do_ssh_command, timeout, Exception, ":")
        self.resume_logging()
        self.logger.debug(f"SSH server active and responsive after {tm.elapsed_time} seconds")

    def wait_for_device_detected(self, timeout=20):
        return self.wait_for_ssh_server_responsive(timeout)

    @thread_lock
    def do_ssh_command(self, command, time_out=10.0, rcvd_timeout=None):
        """
        execute ssh command non-blocking call to library. asynchronous command must be called with rcvd_timeout>None
        warning doesn't return an error
        used for slower/longer responding command like 'ls -Ral /' or avahi-browse.

        Try to avoid using this as it is less stable

        :param command: command to execute. Supports blocking call command like top/tail by timeout.
        :param time_out: total timeout in seconds for command (infinite command should be terminated by this timeout)
        :param rcvd_timeout: timeout in seconds to wait when no data received, default=None then no wait at all"""
        retval = ""
        self.logger.info("running '%s' %s %s %s", command, self.username, _hide_password(self.password), self.address)

        retry = 0
        session = None
        start_time = time.time()
        while time_out > time.time() - start_time and session is None:
            try:
                session = self.ssh_con.get_transport().open_session()
            except (OSError, AuthenticationException, SSHException) as excep:
                self.logger.error("Exception caught after opening session: %s - %s, re-initialize the engine", str(type(excep)), str(excep))

                self.__re_init__()
                session = self.ssh_con.get_transport().open_session()
            except Exception as excep:
                self.logger.error("exception caught of type %s after opening session", str(type(excep)))

                self.logger.error("maybe a reboot was done, will re-initiate session object")
                self.ssh_con = create_ssh_session_obj_from_hostname(self.address, self.username, self.password, self.port)

                self.logger.info("ssh_con object recreated")
                session = self.ssh_con.get_transport().open_session()
                self.logger.info("calling ls /bin/ to check if ssh is open")
                time.sleep(1)
                if self.do_command("ls /bin/").strip() != "":
                    break
                retry += 1
                if retry > 5:
                    raise SSHException("Probably the unit is switched off or rebooting") from excep
        self.logger.debug("now executing %s", command)
        session.exec_command(command)
        time.sleep(0.1)
        if rcvd_timeout is None:
            rcvd_timeout = 0.1
        not_rdy_count = rcvd_timeout * 10
        buf = "THISISANEMPTY_BUFFEROFTHESSHENGINE"
        start_time = time.time()
        while (not_rdy_count > 0 or buf != "") and rcvd_timeout > time.time() - start_time:
            self.logger.debug(
                "Data Count=%d RECV: len=%d [%s], left=%f", not_rdy_count, len(buf), buf, rcvd_timeout - (time.time() - start_time)
            )

            if session.recv_ready():
                buf = decode_to_str_if_byte(session.recv(4 * 4096))
                retval += buf
                if len(buf):
                    not_rdy_count = rcvd_timeout * 10
                if len(retval) > 100000000:
                    raise EmbeddedFrameworkException("return value is larger than 100 MB please do this call via scp")

                self.logger.debug("Data RECV: len=%d, time=%f", len(buf), rcvd_timeout - (time.time() - start_time))

            else:
                time.sleep(0.1)
                buf = ""
                not_rdy_count -= 1
                self.logger.debug("Data not RDY: %f" % (rcvd_timeout - (time.time() - start_time)))

        if session.recv_stderr_ready():
            buf = decode_to_str_if_byte(session.recv_stderr(4096))
            retval += buf
        return retval

    @thread_lock
    def _do_command(self, command, time_out=60, re_init_exceptions=()):
        """
        runs a quick command and returns the stout + stderr (if it exists) as one string

        The time_out parameter is passed to paramiko.SSHClient.exec_command. There are 2 purposes for the timeout.

        - Time limit for opening SSH channel
        - Time limit for blocking reading/writing

        :param command:
        :param time_out: in seconds or None for blocking waiting for response.
        :return: Mixed stdout and stderr
        :rtype: str
        """
        try:
            self.logger.debug("executing %s", command)
            stdout, exit_status, stderr = self._ssh_exec_command_w_timeout(command, time_out)
        except (OSError, AuthenticationException, SSHException, *re_init_exceptions) as excep:
            self.logger.error(
                "Exception caught after opening session in _do_command: %s - %s, re-initialize the engine",
                str(type(excep)),
                str(excep),
            )

            self.__re_init__()
            stdout, exit_status, stderr = self._ssh_exec_command_w_timeout(command, time_out)
        except gevent.hub.LoopExit as excep:
            self.logger.info("caught exception %s %s", str(type(excep)), str(excep))
            return
        except Exception as excep:
            self.logger.error("_do_command recovery: caught exception type %s, message %s", str(type(excep)), str(excep))

            self.ssh_con = create_ssh_session_obj_from_hostname(self.address, self.username, self.password, self.port)

            stdout, exit_status, stderr = self._ssh_exec_command_w_timeout(command, time_out)
        return stdout, exit_status, stderr

    def do_command(self, command, time_out=60):
        stdout, _, stderr = self._do_command(command, time_out=time_out, re_init_exceptions=[SSHCommandFailed])
        ret_val = str(stdout)
        if stderr:
            ret_val += str(stderr)
        self.logger.info(ret_val)
        return ret_val

    def do_command_w_exitstatus(self, command, time_out=60):
        return self._do_command(command, time_out=time_out)

    @thread_lock
    def put_files(self, source, destination):
        """
        sends a file via scp to a server"""
        try:
            self.logger.info("putting %s to %s", source, destination)
            with scp.SCPClient(self.ssh_con.get_transport(), buff_size=16384, socket_timeout=30.0, progress=None) as scp_conn:
                scp_conn.put(source, destination, recursive=True, preserve_times=False)
        except (OSError, AuthenticationException, SSHException, scp.SCPException) as excep:
            self.logger.error("Exception caught after opening session: %s - %s, re-initialize the engine", str(type(excep)), str(excep))
            self.__re_init__()
            self.logger.info("deleting %s before putting the file again", destination)
            cmd = f"rm -f {destination}"
            self.do_command(cmd)
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
            embedded_framework.lib.timeout.TimeOutError: Timeout of 60.0 seconds reached, stopping waiting for regex
            Last line read was:
            '64 bytes from 8.8.8.8: seq=59 ttl=117 time=10.696 ms'
            >>> ssh_engine.send_command_and_wait_for_regex_in_output(
            ...     "ping 8.8.8.8",
            ...     "this wil never appear",
            ...     timeout=50.0,
            ...     suppress=embedded_framework.lib.timeout.TimeOutError,
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
        channel = self.ssh_transport.open_channel(
            "direct-tcpip",
            (self.dest_address, self.dest_port),
            self.request.getpeername(),
        )

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
    :param timeout: Connection timeout in seconds.
    :returns: Connected SSH engine.
    """
    connection = create_ssh_session_obj_from_hostname(address, username, password, port, retry, timeout)
    return SshTransport(connection, address, username, password, port)

