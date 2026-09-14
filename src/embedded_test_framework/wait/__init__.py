"""Bounded polling for caller-selected, repeatable observations."""
import time

from ..core.validation import positive_timeout
from ..errors import OperationTimeout, ObservationFailed
from ..logging import get_logger

logger = get_logger("server", "wait")


def _poll(observe, accept, *, timeout, interval, exceptions):
    deadline = time.monotonic() + positive_timeout(timeout)
    interval = positive_timeout(interval)
    last_error = None
    while True:
        try:
            value = observe()
            if accept(value) and time.monotonic() <= deadline:
                return value
        except exceptions as exc:
            last_error = exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.error("Observation timed out (code=OPERATION_TIMEOUT)")
            raise OperationTimeout("Observation did not satisfy the condition before timeout") from last_error
        time.sleep(min(interval, remaining))


def until_true(observe, *, timeout=30.0, interval=0.5, exceptions=()):
    return _poll(observe, bool, timeout=timeout, interval=interval, exceptions=exceptions)


def until_false(observe, *, timeout=30.0, interval=0.5, exceptions=()):
    return _poll(observe, lambda value: not value, timeout=timeout, interval=interval, exceptions=exceptions)


def until_equal(observe, expected, *, timeout=30.0, interval=0.5, exceptions=()):
    return _poll(observe, lambda value: value == expected, timeout=timeout, interval=interval, exceptions=exceptions)


def until_no_exception(observe, *, exceptions, timeout=30.0, interval=0.5):
    """Retry only explicitly selected exceptions; never used implicitly for writes."""
    return _poll(observe, lambda value: True, timeout=timeout, interval=interval, exceptions=exceptions)


def stays_true(observe, *, duration=5.0, interval=0.5):
    return stays_equal(lambda: bool(observe()), True, duration=duration, interval=interval)


def stays_equal(observe, expected, *, duration=5.0, interval=0.5):
    """Sample through the duration, failing at the first mismatch (not continuous monitoring)."""
    deadline = time.monotonic() + positive_timeout(duration)
    interval = positive_timeout(interval)
    while True:
        value = observe()
        if value != expected:
            logger.error("Stability observation failed (code=OBSERVATION_FAILED)")
            raise ObservationFailed("Observed value changed during the stability window")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return value
        time.sleep(min(interval, remaining))
