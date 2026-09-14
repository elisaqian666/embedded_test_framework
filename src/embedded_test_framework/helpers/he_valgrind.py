"""
This module contains helper functions for using the valgrind tool.
"""
import shlex
from .helper_base import Helper
from ..libs.errors import ConfigurationError


class ValgrindHelper(Helper):
    """Run an explicitly supplied program under Valgrind on a connected Linux DUT."""
    def __init__(self, device, *, channel="shell"):
        self.device, self.channel = device, channel

    def run(self, args, *, timeout=60):
        if not isinstance(args, (list, tuple)) or not args or any(not isinstance(arg, str) for arg in args):
            raise ConfigurationError("Valgrind requires a nonempty argument list")
        command = shlex.join(["valgrind", "--error-exitcode=99", "--leak-check=full", "--", *args])
        return self.device.execute(command, channel=self.channel, timeout=timeout)
