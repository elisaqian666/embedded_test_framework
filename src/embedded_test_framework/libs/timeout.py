"""Cooperative deadline budgets; this does not terminate threads or functions."""
import time

from ..libs.validation import positive_timeout
from .errors import OperationTimeout


class Deadline:
    def __init__(self, seconds):
        self._end = time.monotonic() + positive_timeout(seconds)

    @property
    def remaining(self):
        return max(0.0, self._end - time.monotonic())

    @property
    def expired(self):
        return self.remaining <= 0

    def check(self):
        remaining = self.remaining
        if remaining <= 0:
            raise OperationTimeout("Operation deadline expired")
        return remaining

    def sleep(self, seconds):
        delay = positive_timeout(seconds)
        time.sleep(min(delay, self.check()))
        self.check()
