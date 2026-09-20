"""Common host, file, network and polling helpers without product dependencies."""

import hashlib
import logging
import socket
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from embedded_framework.helpers.he_host_pc import ContentHandler, SystemHelper
from embedded_framework.lib.timeout import TimeoutParams, wait_timeout

logger = logging.getLogger(__name__)


class FileHelper:
    """Host-side file operations, extracted from the host PC helper's common tasks."""

    @staticmethod
    def checksum(path: str | Path, algorithm: str = "sha256") -> str:
        """Hash a file incrementally; memory usage does not depend on file size."""
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, algorithm).hexdigest()

    @staticmethod
    def are_files_identical(first: str | Path, second: str | Path) -> bool:
        """Compare regular files; return False when either file does not exist."""
        left, right = Path(first), Path(second)
        return (
            left.is_file()
            and right.is_file()
            and left.stat().st_size == right.stat().st_size
            and FileHelper.checksum(left) == FileHelper.checksum(right)
        )

    @staticmethod
    def read_text(path: str | Path, encoding: str = "utf-8") -> str:
        """Read a local text file with an explicit encoding."""
        return Path(path).read_text(encoding=encoding)

    @staticmethod
    def write_text(path: str | Path, content: str, encoding: str = "utf-8") -> Path:
        """Create parent directories and write a local text file."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding=encoding)
        return destination


class HostHelper:
    """Run host programs using argument lists, preserving stdout, stderr and exit status."""

    @staticmethod
    def run(
        args: Sequence[str],
        *,
        timeout: float = 30,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a program without a host shell.

        :param args: Executable followed by separate arguments, not a command string.
        :param timeout: Finite subprocess timeout in seconds.
        :param cwd: Optional working directory.
        :param env: Optional complete environment mapping, following subprocess.run.
        :param check: Raise CalledProcessError on non-zero exit if True.
        :returns: Captured stdout, stderr and return code.
        """
        if isinstance(args, (str, bytes)) or not args or timeout <= 0:
            message = "args must be a non-empty argument sequence and timeout must be positive"
            raise ValueError(message)
        return subprocess.run(  # noqa: S603 - explicit caller-provided argv; shell execution is disabled
            args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd, env=env, check=check
        )


class CommonHelpers:
    """Small helper collection exposed by a runtime and each DUT."""

    def __init__(self) -> None:
        self.content = ContentHandler()
        self.files = FileHelper()
        self.host = HostHelper()
        self.network = NetworkHelper()
        self.system = SystemHelper()

    @staticmethod
    def wait_until(predicate: Callable[..., Any], *args: Any, timeout: float = 30, interval: float = 0.2, **kwargs: Any) -> Any:
        """Poll a callable until truthy, forwarding its arguments and returning its value."""
        if timeout < 0 or interval <= 0:
            message = "timeout must be non-negative and interval must be positive"
            raise ValueError(message)

        def invoke() -> Any:
            return predicate(*args, **kwargs)

        return wait_timeout(invoke, TimeoutParams(timeout, None, interval))
