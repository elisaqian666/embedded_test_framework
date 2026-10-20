"""Common POSIX shell operations for devices that expose an SSH command engine."""

import asyncio
import json
import logging
import math
import shlex
from collections.abc import AsyncIterator
from typing import Any

from embedded_test_framework.configurator.config_labels import LOGGERS
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import SSHCommandError


class LinuxHelper:
    """Common POSIX shell operations executed through an SSH engine."""

    def __init__(self, engine: Any) -> None:
        if not callable(getattr(engine, "exec_command", None)):
            raise TypeError("Shell engine must provide exec_command()")
        self.engine = engine
        self.logger = logging.getLogger(LOGGERS.HELPER)

    def execute(self, command: str, timeout: float | None = None, *, check: bool = True) -> CommandResult:
        """Run a trusted shell command and retain stdout, stderr and exit status.

        Shell syntax is intentional here; use run_program() for literal arguments.
        Timeout is forwarded to the SSH engine, not a remote process lifetime limit.
        """
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise ValueError("command must be a non-empty string without NUL characters")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0
        ):
            raise ValueError("timeout must be a finite positive number")
        if type(check) is not bool:
            raise TypeError("check must be bool")
        result = self.engine.exec_command(command, timeout=timeout)
        return result.check(SSHCommandError) if check else result

    shell = execute

    def service(self, name: str, action: str, *, timeout: float | None = None) -> CommandResult:
        if not isinstance(name, str) or not name or "\x00" in name or action not in {"start", "stop", "restart", "status"}:
            raise ValueError("service name and action must be valid")
        return self.execute(f"systemctl {action} -- {shlex.quote(name)}", timeout=timeout, check=action != "status")

    def get_kernel_version(self, timeout: float | None = None) -> str:
        """Return the kernel release (uname -r), e.g. '6.6.12-custom'."""
        version = self.execute("uname -r", timeout).stdout.strip()
        if not version:
            raise RuntimeError("uname -r returned an empty kernel version")
        return version

    def run_program(self, program: str, *args: str, timeout: float | None = None, check: bool = True) -> CommandResult:
        """Run a program in the foreground, quoting each argument literally.

        Bare names are looked up in PATH; use './app' for a local executable.
        No shell expansion, sudo, permission changes or backgrounding is implicit.
        """
        if not isinstance(program, str) or not program or "\x00" in program:
            raise ValueError("program must be a non-empty string without NUL characters")
        if any(not isinstance(arg, str) or "\x00" in arg for arg in args):
            raise ValueError("program arguments must be strings without NUL characters")
        executable = self._path(program) if "/" in program or program.startswith("-") else shlex.quote(program)
        # exec prevents a bare shell keyword or assignment from being parsed as shell syntax.
        command = "exec " + executable
        if args:
            command += " " + shlex.join(args)
        return self.execute(command, timeout, check=check)

    def make_executable(self, path: str, timeout: float | None = None) -> CommandResult:
        """Add owner execute permission (chmod u+x), preserving other permission bits."""
        return self.execute(f"chmod u+x {self._path(path)}", timeout)

    async def _run_network_program(self, program: str, *args: str, deadline: int) -> CommandResult:
        """Bound remote execution and drain the SSH worker before allowing cleanup."""
        task = asyncio.create_task(
            asyncio.to_thread(self.run_program, "timeout", "-k", "2", str(deadline), program, *args, timeout=deadline + 10, check=False)
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                pass  # Preserve cancellation after the SSH worker has finished.
            raise

    @staticmethod
    def _network_host(host: str) -> None:
        if not isinstance(host, str) or not host or host.startswith("-") or any(c.isspace() or c == "\x00" for c in host):
            raise ValueError("host must be a non-empty hostname/IP without whitespace, NUL or a leading dash")

    async def iperf(self, server: str, *, direction: str = "upload", duration: int = 10, port: int = 5201) -> dict[str, Any]:
        """Run a finite TCP iperf3 test on the DUT and return its native JSON report.

        upload: DUT -> server; download: server -> DUT; bidirectional: simultaneous.
        Requires remote iperf3 and GNU timeout. The peer server must already be running.
        Cancellation waits for the bounded command; a shared SSH engine serializes calls.
        """
        self._network_host(server)
        if direction not in ("upload", "download", "bidirectional"):
            raise ValueError("direction must be upload, download, or bidirectional")
        if type(duration) is not int or duration <= 0:
            raise ValueError("duration must be a positive integer in seconds")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be an integer in [1, 65535]")
        args = ["-c", server, "-p", str(port), "-t", str(duration), "-J"]
        if direction == "download":
            args.append("-R")
        elif direction == "bidirectional":
            args.append("--bidir")
        result = await self._run_network_program("iperf3", *args, deadline=duration + 10)
        result.check(SSHCommandError)
        report = json.loads(result.stdout)
        if not isinstance(report, dict):
            raise ValueError("iperf3 returned a non-object JSON report")
        if "error" in report:
            raise RuntimeError(f"iperf3 failed: {report['error']}")
        return report

    async def ping(self, host: str, *, interval: float = 1, reply_timeout: int = 1) -> AsyncIterator[CommandResult]:
        """Yield one Linux iputils ping result repeatedly until closed/cancelled.

        Status 0 means reply, 1 means no reply; other statuses raise. interval is
        the delay after consumption of each result, not a fixed packet frequency.
        Requires remote ping and GNU timeout. No results are accumulated internally.
        """
        self._network_host(host)
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval < 0:
            raise ValueError("interval must be a finite non-negative number")
        if type(reply_timeout) is not int or reply_timeout <= 0:
            raise ValueError("reply_timeout must be a positive integer in seconds")
        while True:
            result = await self._run_network_program("ping", "-n", "-c", "1", "-W", str(reply_timeout), host, deadline=reply_timeout + 2)
            if result.exit_status not in (0, 1):
                result.check(SSHCommandError)
            yield result
            await asyncio.sleep(interval)

    def _execute(self, command: str, timeout: float | None = None) -> str:
        """Execute a command on the remote device."""
        self.logger.debug("Executing command: %s", command)
        return self.execute(command, timeout).stdout

    @staticmethod
    def _path(path: str) -> str:
        """Validate and quote a remote path."""
        if not isinstance(path, str) or not path or "\x00" in path:
            raise ValueError("Remote path must be non-empty and contain no NUL characters")

        # Prefix relative paths so names starting with '-' cannot become options.
        return shlex.quote(path if path.startswith("/") else "./" + path)

    def read_text(self, path: str, timeout: float | None = None) -> str:
        """Read a remote text file."""
        return self._execute(f"cat {self._path(path)}", timeout)

    def exists_file(self, path: str, timeout: float | None = None) -> bool:
        """Return whether a regular remote file exists."""
        output = self._execute(f"test -f {self._path(path)} && echo 1 || echo 0", timeout)
        return output.strip() == "1"

    def exists_dir(self, path: str, timeout: float | None = None) -> bool:
        """Return whether a remote directory exists."""
        output = self._execute(f"test -d {self._path(path)} && echo 1 || echo 0", timeout)
        return output.strip() == "1"

    def exists(self, path: str, timeout: float | None = None) -> bool:
        """Return whether a remote path exists."""
        output = self._execute(f"test -e {self._path(path)} && echo 1 || echo 0", timeout)
        return output.strip() == "1"

    def create_dir(self, path: str, timeout: float | None = None) -> str:
        """Create a remote directory and missing parents."""
        return self._execute(f"mkdir -p {self._path(path)}", timeout)

    def copy_file(self, source: str, destination: str, timeout: float | None = None) -> str:
        """Copy a remote file."""
        return self._execute(f"cp {self._path(source)} {self._path(destination)}", timeout)

    def move_file(self, source: str, destination: str, timeout: float | None = None) -> str:
        """Move a remote file."""
        return self._execute(f"mv {self._path(source)} {self._path(destination)}", timeout)

    def remove_file(self, path: str, timeout: float | None = None) -> str:
        """Remove one remote file."""
        return self._execute(f"rm {self._path(path)}", timeout)

    def _meminfo_kb(self, field: str, timeout: float | None = None) -> int:
        """Read one numeric field from /proc/meminfo in KiB."""
        output = self._execute(f"awk '/^{field}:/ {{print $2}}' /proc/meminfo", timeout).strip()

        if not output:
            raise RuntimeError(f"{field} not found in /proc/meminfo")

        return int(output)

    def get_total_memory(self, timeout: float | None = None) -> int:
        """Return total system memory in KiB."""
        return self._meminfo_kb("MemTotal", timeout)

    def get_available_memory(self, timeout: float | None = None) -> int:
        """Return estimated available system memory in KiB."""
        return self._meminfo_kb("MemAvailable", timeout)

    def get_free_memory(self, timeout: float | None = None) -> int:
        """Return completely unused system memory in KiB."""
        return self._meminfo_kb("MemFree", timeout)

    def get_process_memory(self, pid: int, timeout: float | None = None) -> int:
        """Return process resident memory (VmRSS) in KiB."""
        if type(pid) is not int or pid <= 0:
            raise ValueError("pid must be positive")

        output = self._execute(f"awk '/^VmRSS:/ {{print $2}}' /proc/{pid}/status", timeout).strip()

        if not output:
            raise RuntimeError(f"VmRSS not found for process {pid}")

        return int(output)

    def get_process_memory_by_name(self, name: str, timeout: float | None = None) -> int:
        """Return total RSS in KiB for all matching processes."""
        if not name or "\x00" in name:
            raise ValueError("Process name must be non-empty and contain no NUL characters")

        output = self._execute(f"ps -C {shlex.quote(name)} -o rss= 2>/dev/null", timeout)

        return sum(int(value) for value in output.split() if value.isdigit())

    def kill_process(self, process: int, timeout: float | None = None) -> CommandResult:
        """Send SIGTERM to one positive PID; success means sent, not confirmed exited."""
        if type(process) is not int or process <= 0:
            raise ValueError("process must be a positive integer PID")
        return self.execute(f"kill -s TERM {process}", timeout)


if __name__ == "__main__":

    class FakeEngine:
        def exec_command(self, command: str, timeout: float | None = None) -> CommandResult:
            if "/proc/meminfo" in command:
                return CommandResult("1024000\n")

            if "/proc/123/status" in command:
                return CommandResult("20480\n")

            return CommandResult()

    helper = LinuxHelper(FakeEngine())

    assert helper.get_total_memory() == 1024000
    assert helper.get_process_memory(123) == 20480

    print("self-check passed")
