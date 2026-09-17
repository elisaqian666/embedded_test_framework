"""Purpose: Provide reusable assertion functions for system tests."""

import re
from collections.abc import Callable, Container, Iterator
from contextlib import contextmanager
from typing import Any

from embedded_framework.lib.timeout import (
    TimeOutError,
    TimeoutParams,
    wait_equal_timeout,
    wait_false_timeout,
    wait_timeout,
    wait_until_in_timeout,
    wait_until_not_in_timeout,
)
from embedded_framework.lib.watch import DEFAULT_NO_SPAM_SLEEP


def assert_equal(actual: Any, expected: Any, msg: str | None = None) -> None:
    """Require equal values; remains active under python -O."""
    if actual != expected:
        raise AssertionError(msg if msg is not None else f"Expected {expected!r}, got {actual!r}")


def assert_true(value: Any, msg: str | None = None) -> None:
    """Require a truthy value."""
    if not value:
        raise AssertionError(msg if msg is not None else f"Expected a truthy value, got {value!r}")


assertEqual = assert_equal
assertTrue = assert_true


def assert_false(value: Any, msg: str | None = None) -> None:
    """Require a falsy value."""
    if value:
        raise AssertionError(msg if msg is not None else f"Expected a falsy value, got {value!r}")


def assert_in(member: Any, container: Container[Any], msg: str | None = None) -> None:
    """Require a value to occur in a collection or string."""
    if member not in container:
        raise AssertionError(msg if msg is not None else f"{member!r} was not found in {container!r}")


def assert_matches(text: str, pattern: str, msg: str | None = None) -> re.Match[str]:
    """Require a regex match and return the matching object."""
    match = re.search(pattern, text)
    if match is None:
        raise AssertionError(msg if msg is not None else f"Pattern {pattern!r} did not match")
    return match


@contextmanager
def assert_raises(exception: type[Exception]) -> Iterator[None]:
    """Require the specified exception; an unexpected exception propagates unchanged."""
    try:
        yield
    except exception:
        return
    message = f"Expected {exception.__name__} to be raised"
    raise AssertionError(message)


def assert_eventually(
    predicate: Callable[[], Any], *, timeout: float = 30, interval: float = DEFAULT_NO_SPAM_SLEEP, msg: str | None = None
) -> Any:
    """Poll a predicate using existing timeout logic and convert expiry to AssertionError."""
    if timeout < 0 or interval <= 0:
        message = "timeout must be non-negative and interval must be positive"
        raise ValueError(message)

    def invoke() -> Any:
        return predicate()

    try:
        return wait_timeout(invoke, TimeoutParams(timeout, msg, interval))
    except TimeOutError as error:
        raise AssertionError(str(error)) from error


def assert_equal_timeout(func_which_should_evaluate_to_value, value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs):
    """runs a function until it returns a value within the timeout, asserts if timeout is passed (sleeps interval of secs between each try)

    :param func_which_should_evaluate_to_value: function to execute as a function object
    :type func_which_should_evaluate_to_value: Callable
    :param value: value to which the function should evaluate to
    :param timeout: timeout as an int in seconds (though library supports timeout and  TimeoutParams(tm,msg,intv) as timeout)
    :param msg: error message as an string
    :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
    :param args: extra arguments needed for the function to run
    :param kwargs: extra keyword arguments needed for the function to run
    :returns: the value returned by ``func_which_should_evaluate_to_value`` once it matches ``value``
    :raises AssertionError: if ``value`` is not reached before ``timeout`` expires

    Example::

        >>> assert_equal_timeout(device.get_status, "connected", timeout=30)
        'connected'
    """
    try:
        return wait_equal_timeout(func_which_should_evaluate_to_value, TimeoutParams(timeout, msg, interval), value, *args, **kwargs)
    except TimeOutError as err:
        raise AssertionError(err) from err


def assert_true_timeout(
    predicate: Callable[..., Any],
    *args: Any,
    timeout: float = 0,
    msg: str | None = None,
    interval: float = DEFAULT_NO_SPAM_SLEEP,
    **kwargs: Any,
) -> Any:
    """Require a callable to become truthy, preserving the existing timeout diagnostics."""
    try:
        return wait_timeout(predicate, TimeoutParams(timeout, msg, interval), *args, **kwargs)
    except TimeOutError as error:
        raise AssertionError(str(error)) from error


def assert_false_timeout(
    predicate: Callable[..., Any],
    *args: Any,
    timeout: float = 0,
    msg: str | None = None,
    interval: float = DEFAULT_NO_SPAM_SLEEP,
    **kwargs: Any,
) -> Any:
    """Require a callable to become falsy within the timeout."""
    try:
        return wait_false_timeout(predicate, TimeoutParams(timeout, msg, interval), *args, **kwargs)
    except TimeOutError as error:
        raise AssertionError(str(error)) from error


def assert_in_timeout(
    predicate: Callable[..., Any],
    value: Any,
    *args: Any,
    timeout: float = 0,
    msg: str | None = None,
    interval: float = DEFAULT_NO_SPAM_SLEEP,
    **kwargs: Any,
) -> Any:
    """Require a value to occur in a callable's result within the timeout."""
    try:
        return wait_until_in_timeout(predicate, TimeoutParams(timeout, msg, interval), value, *args, **kwargs)
    except TimeOutError as error:
        raise AssertionError(str(error)) from error


def assert_not_in_timeout(func_which_should_evaluate_to_value, value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs):
    """Wait until the returned value no longer contains the sentinel; assert if the timeout expires.

    :param func_which_should_evaluate_to_value: function to execute as a function object
    :type func_which_should_evaluate_to_value: Callable
    :param value: sentinel value that must not be present in the return value
    :param timeout: timeout as an int in seconds (though library supports timeout and  TimeoutParams(tm,msg,intv) as timeout)
    :param msg: error message as an string
    :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
    :param args: extra arguments needed for the function to run
    :param kwargs: extra keyword arguments needed for the function to run
    :returns: the value returned by ``func_which_should_evaluate_to_value`` once it no longer contains ``value``
    :raises AssertionError: if ``value`` is still present in the return value before ``timeout`` expires

    Example::

        >>> assert_not_in_timeout(device.get_status, "disconnected", timeout=30)
        ['connected']
    """
    try:
        return wait_until_not_in_timeout(func_which_should_evaluate_to_value, TimeoutParams(timeout, msg, interval), value, *args, **kwargs)
    except TimeOutError as err:
        raise AssertionError(err) from err
