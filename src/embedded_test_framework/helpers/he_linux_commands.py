"""
Purpose: Encapsulate some commonly used Linux commands, like grep, move_file, mount, etc.
"""
import shlex
from .helper_base import Helper


class LinuxCommandHelper(Helper):
    """Linux shell helpers using a connected Device and safely quoted arguments."""
    def __init__(self, device, *, channel="shell"):
        self.device = device
        self.channel = channel

    def _execute(self, command, timeout):
        return self.device.execute(command, channel=self.channel, timeout=timeout).check()

    def kernel_version(self, *, timeout=None):
        return self._execute("uname -r", timeout).stdout.strip()

    def read_file(self, path, *, timeout=None):
        return self._execute("cat -- " + shlex.quote(str(path)), timeout).stdout

    def path_exists(self, path, *, timeout=None):
        result = self.device.execute("test -e " + shlex.quote(str(path)), channel=self.channel, timeout=timeout)
        if result.exit_code not in (0, 1):
            result.check()
        return result.exit_code == 0

    def move_file(self, source, destination, *, timeout=None):
        return self._execute("mv {} {}".format(shlex.quote(str(source)), shlex.quote(str(destination))), timeout)

    def remove_file(self, file_path, *, timeout=None):
        return self._execute("rm {}".format(shlex.quote(str(file_path))), timeout)
