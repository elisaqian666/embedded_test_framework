"""Transport-independent result of one completed command."""


class CommandResult:
    """Command output, exit code and elapsed wall time in seconds.

    exit_status remains an alias for callers using the previous API.
    duration defaults to zero for results constructed without timing information.
    """

    def __init__(
        self, stdout: str = "", exit_code: int = 0, stderr: str = "", duration: float = 0.0, *, exit_status: int | None = None
    ) -> None:
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.exit_code = int(exit_code if exit_status is None else exit_status)
        self.duration = float(duration)

    @property
    def exit_status(self) -> int:
        return self.exit_code

    @exit_status.setter
    def exit_status(self, value: int) -> None:
        self.exit_code = int(value)

    def check(self, error_type: type[RuntimeError] = RuntimeError) -> "CommandResult":
        if self.exit_code != 0:
            raise error_type(f"Command failed with exit status {self.exit_code}. stderr={self.stderr!r} stdout={self.stdout!r}")
        return self

    def __bool__(self) -> bool:
        return self.exit_code == 0

    def __str__(self) -> str:
        return self.stdout or self.stderr or ""
