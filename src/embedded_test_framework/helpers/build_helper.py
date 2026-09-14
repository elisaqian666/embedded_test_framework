"""Explicit host build commands; no automatic shell interpretation."""
from .helper_base import Helper


class BuildHelper(Helper):
    def __init__(self, host):
        self.host = host

    def run(self, args, *, cwd=None, timeout=300):
        return self.host.run(args, cwd=cwd, timeout=timeout).check()
