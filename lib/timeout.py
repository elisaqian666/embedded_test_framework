"""Purpose: Provide timeout and retry utilities."""

import logging
import time
from collections import namedtuple
from contextlib import suppress

from embedded_framework.lib.basic_helper_functions import get_parent_that_defined_method, listify
from embedded_framework.lib.custom_exception import EmbeddedFrameworkException
from embedded_framework.lib.timer import Timer

logger = logging.getLogger("timeout")

DEFAULT_NO_SPAM_SLEEP = 0.15
TimeoutParams = namedtuple("TimeoutParams", ["timeout", "timeout_msg", "no_spam_sleep"])
TimeoutParams.__new__.__defaults__ = (None, DEFAULT_NO_SPAM_SLEEP)


def empty_debug_func():
    return ""


class TimeOutError(EmbeddedFrameworkException):
    """A timeout raised by framework operations."""

    def __init__(self, message=""):
        super().__init__(message)
        self.message = message

    def __repr__(self):
        return self.message


def get_timeout_params(timeout_param):
    """
    Gets the parameters from timeout_param.  This is either number indicating the timeout for the timeout function or holds more
    information such a the delay between consecutive tests and the specific failure message replacing the standard one.

    :param timeout_param: Either just a number or an instance of TimeoutParams.
    :return: (timeout_msg, no_spam_sleep, timeout)
    """
    if isinstance(timeout_param, TimeoutParams):
        timeout = timeout_param.timeout
        timeout_msg = timeout_param.timeout_msg
        no_spam_sleep = timeout_param.no_spam_sleep
    else:
        timeout = timeout_param
        timeout_msg = None
        no_spam_sleep = DEFAULT_NO_SPAM_SLEEP
    return timeout_msg, no_spam_sleep, timeout


def get_timeout_excep_msg(func, ret_val, msg, timedout_after, timeout, expected, args, kwargs):
    """return timeout exception messages"""
    default_timeout_msg = (
        f"Timed out after {timedout_after} seconds (max allowed {timeout}),\n"
        f'executing "{_get_function_path_and_name_and_params(func, args, kwargs)}",\n'
        f'Expecting:\n"{expected}"\nbut on the last call it returned:\n"{ret_val}"'
    )

    return f"{msg} :\n{default_timeout_msg}" if msg else default_timeout_msg


def __debug_logging(func, ret_val):
    logger.debug('Called: "%s()", return value: %s', func.__name__, str(ret_val))


def _get_args_kwargs_string(args, kwargs):
    args_string = str(args).replace("(", "").replace(")", "")
    kwargs_string = str(kwargs).replace("{", "").replace("}", "").replace(": ", "=").replace("'", "")
    return f"{args_string.rstrip(',') or ''}{', ' if args_string and kwargs_string else ''}{kwargs_string or ''}"


def wait_timeout(func, timeout_param, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns a value that would evaluate to True by bool() or timeout is reached

    :param func: callable object
    :type func: Callable
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    :param debug_info_func: a callable object which will be called whenever there is a timeout error. It should return a string which will be added to the exception
    """
    debug_func = kwargs.pop("debug_info_func", empty_debug_func)
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val:  # Will return on not None, False, empty
            return ret_val
        if timer.timeout_expired:
            debug_string = str(debug_func())
            debug_message = "\nExtra debug info:\n" + debug_string if debug_string else ""
            expected = f"{_get_function_path_and_name_and_params(func, args, kwargs)} to evaluate to True"
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
                + debug_message
            )
        time.sleep(no_spam_sleep)


def with_timeout(func):
    """
    Decorator to repetitively call any function until it returns a value that would evaluate to True by bool() or timeout is reached
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, *args, **kwargs):
        """

        Wrapper to repetitively call any function until it returns a value that would evaluate to True by bool() or timeout is reached.
        It steals the first argument, the rest is passed to the function being wrapped.

        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_timeout(func, timeout_param, *args, **kwargs)

    return func_wrapper


def wait_false_timeout(func, timeout_param, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns a value that would evaluate to False by bool() or timeout is reached

    :param func: callable object
    :type func: Callable
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    debug_func = kwargs.pop("debug_info_func", empty_debug_func)
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if not ret_val:  # Will return on None, False, empty
            return ret_val
        if timer.timeout_expired:
            expected = f"{_get_function_path_and_name_and_params(func, args, kwargs)} to evaluate to False"
            debug_string = str(debug_func())
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
                + debug_string
            )
        time.sleep(no_spam_sleep)


def with_timeout_false(func):
    """
    Decorator to repetitively call any function until it returns a value that would evaluate to False by bool() or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, *args, **kwargs):
        """
        Wrapper to repetitively call any function until:
        - it returns a value that would evaluate to False by bool()
        - the timeout is reached.
        It steals the first argument, the rest is passed to the function being wrapped.

        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_false_timeout(func, timeout_param, *args, **kwargs)

    return func_wrapper


def wait_equal_timeout(func, timeout_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :type func: Callable
    :param sentinel_value: this will call func until the return value = sentinel_value unless timeout is reached
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    debug_func = kwargs.pop("debug_info_func", empty_debug_func)
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val == sentinel_value:
            return ret_val
        if timer.timeout_expired:
            debug_string = str(debug_func())
            expected = f"{_get_function_path_and_name_and_params(func, args, kwargs)} == '{sentinel_value}'"
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
                + debug_string
            )
        time.sleep(no_spam_sleep)


def with_timeout_equal(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until sentinel value is received or timeout
        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_equal_timeout(func, timeout_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def wait_not_equal_timeout(func, timeout_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :type func: Callable
    :param sentinel_value: this will call func until the return value != sentinel_value unless timeout is reached
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val != sentinel_value:
            return ret_val
        if timer.timeout_expired:
            expected = f"{_get_function_path_and_name_and_params(func, args, kwargs)} != '{sentinel_value}'"
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
            )
        time.sleep(no_spam_sleep)


def with_timeout_not_equal(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until received value differs from sentinel value or timeout
        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_not_equal_timeout(func, timeout_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def wait_greater_timeout(func, timeout_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :type func: Callable
    :param sentinel_value: this will call func until the return value > sentinel_value unless timeout is reached
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                        - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                        - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val > sentinel_value:
            return ret_val
        if timer.timeout_expired:
            expected = f"{_get_function_path_and_name_and_params(func, args, kwargs)} > '{sentinel_value}'"
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
            )
        time.sleep(no_spam_sleep)


def _get_function_path_and_name_and_params(func, args, kwargs):
    argskwargs = _get_args_kwargs_string(args, kwargs)
    return ".".join((get_parent_that_defined_method(func), func.__name__)) + f"({argskwargs})"


def with_timeout_greater(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until sentinel value is received or timeout
        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_greater_timeout(func, timeout_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def wait_startswith_timeout(func, timeout_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :type func: Callable
    :param sentinel_value: this will call func until the return value starts with the sentinel_value unless timeout is reached
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    expected = f"{_get_function_path_and_name_and_params(func, args, kwargs)}.startswith('{sentinel_value}') == True"
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val.startswith(sentinel_value):
            return ret_val
        if timer.timeout_expired:
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
            )
        time.sleep(no_spam_sleep)


def with_timeout_startswith(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until received value differs from sentinel value or timeout
        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_startswith_timeout(func, timeout_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def wait_until_in_timeout(func, timeout_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :type func: Callable
    :param sentinel_value: this will call func until sentinel value is in the return value unless timeout is reached
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if sentinel_value in ret_val:
            return ret_val
        if timer.timeout_expired:
            expected = f"'{sentinel_value}' in {_get_function_path_and_name_and_params(func, args, kwargs)}"
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
            )
        time.sleep(no_spam_sleep)


def with_timeout_until_in(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until sentinel value is in return value or timeout
        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_until_in_timeout(func, timeout_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def wait_until_not_in_timeout(func, timeout_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :type func: Callable
    :param sentinel_value: this will call func until the return value does not contain the sentinel_value unless timeout is reached
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if sentinel_value not in ret_val:
            return ret_val
        if timer.timeout_expired:
            expected = f"'{sentinel_value}' not in {_get_function_path_and_name_and_params(func, args, kwargs)}"
            raise TimeOutError(
                message=get_timeout_excep_msg(func, ret_val, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
            )
        time.sleep(no_spam_sleep)


def with_timeout_until_not_in(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(timeout_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until sentinel value is not in the received value or timeout
        :param timeout_param: either int in seconds or TimeoutParams named tuple :
            if int : a TimeOutError exception will be raised when timeout_param seconds are expired else
            if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return wait_until_not_in_timeout(func, timeout_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def wait_no_exception_timeout(func, timeout_param, sentinel_exceptions, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it doesn't trigger an exception anymore

    :param func: callable object
    :type func: Callable
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    :param sentinel_exceptions: The exception or list of exceptions we expect to be thrown (and which will keep on looping)
    :param args: args of callable
    :param kwargs: kwargs of callable
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    list_of_sentinel_exceptions = listify(sentinel_exceptions)
    expected = f"no exception raised of type '{sentinel_exceptions}' by {_get_function_path_and_name_and_params(func, args, kwargs)}"
    while True:
        ret_val = None
        with suppress(*list_of_sentinel_exceptions):
            ret_val = func(*args, **kwargs)
            return ret_val
        if timer.timeout_expired:
            try:
                ret_val = func(*args, **kwargs)
                return ret_val
            except Exception as excep:
                excep_info = f"an Exception of type{type(excep)} with error: {excep}"
                raise TimeOutError(
                    message=get_timeout_excep_msg(func, excep_info, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
                ) from excep
        time.sleep(no_spam_sleep)


def with_timeout_no_exception(func):
    """
    Decorator to repetitively call any function until it doesn't trigger an exception anymore
    For now these decorators do not work for methods (function inside classes.
    """

    def func_wrapper(timeout_param, sentinel_exception, *args, **kwargs):
        """wrapper function with_timeout_no_exception"""
        return wait_no_exception_timeout(func, timeout_param, sentinel_exception, *args, **kwargs)

    return func_wrapper


def wait_no_exception_backoff_timeout(
    func,
    timeout_param,
    sentinel_exceptions,
    *args,
    initial_sleep: float = 1.0,
    backoff_factor: float = 2.0,
    max_sleep: float = 60.0,
    **kwargs,
):
    """
    Wrapper to repetitively call any function until it stops raising a sentinel exception,
    backing off exponentially between attempts instead of using a fixed polling interval.

    On the first sentinel exception the caller sleeps ``initial_sleep`` seconds, then doubles
    the delay on every subsequent failure up to ``max_sleep`` seconds per attempt.  The sleep
    is additionally capped to the time remaining before ``timeout_param`` expires, so the loop
    never sleeps past the deadline.

    If ``timeout_param`` is a :class:`TimeoutParams` instance and ``initial_sleep`` was left at
    its default, ``TimeoutParams.no_spam_sleep`` is used to seed the first backoff delay instead
    of the ``1.0`` second default — this keeps the initial retry interval consistent with the
    other ``wait_*_timeout`` helpers. Passing an explicit ``initial_sleep`` always takes
    precedence over ``no_spam_sleep``.

    :param func: Callable to invoke repeatedly.
    :type func: Callable
    :param timeout_param: Either an ``int`` / ``float`` in seconds or a :class:`TimeoutParams`
        named tuple.  A :class:`TimeOutError` is raised when the budget is exhausted.
    :param sentinel_exceptions: The exception type (or list of types) that will be retried.
        Any other exception propagates immediately.
    :param initial_sleep: Seconds to sleep after the first failure. Defaults to ``1.0``; when
        left at this default and ``timeout_param`` is a :class:`TimeoutParams`, its
        ``no_spam_sleep`` value is used instead.
    :param backoff_factor: Multiplier applied to the sleep duration after each failure.
        Defaults to ``2.0`` (i.e. standard exponential backoff).
    :param max_sleep: Upper bound on the per-attempt sleep in seconds. Defaults to ``60.0``.
    :param args: Positional arguments forwarded to *func*.
    :param kwargs: Keyword arguments forwarded to *func*.
    :raises TimeOutError: When *func* has not succeeded before *timeout_param* is exhausted.

    Example::

        >>> wait_no_exception_backoff_timeout(
        ...     server.reconfig_node, 300, requests.exceptions.HTTPError,
        ...     node_name, config_xml,
        ...     initial_sleep=1.0, backoff_factor=2.0, max_sleep=60.0,
        ... )
    """
    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    list_of_sentinel_exceptions = listify(sentinel_exceptions)
    expected = f"no exception raised of type '{sentinel_exceptions}' by {_get_function_path_and_name_and_params(func, args, kwargs)}"
    sleep_duration = no_spam_sleep if isinstance(timeout_param, TimeoutParams) and initial_sleep == 1.0 else initial_sleep

    # Loop exits on its own condition (budget not yet exhausted) rather than relying on an
    # internal break/return buried inside a `while True:`.
    while not timer.timeout_expired:
        with suppress(*list_of_sentinel_exceptions):
            return func(*args, **kwargs)
        actual_sleep = min(sleep_duration, timer.remaining_time)
        time.sleep(max(0.0, actual_sleep))
        sleep_duration = min(sleep_duration * backoff_factor, max_sleep)

    try:
        return func(*args, **kwargs)
    except Exception as excep:
        excep_info = f"an Exception of type {type(excep)} with error: {excep}"
        raise TimeOutError(
            message=get_timeout_excep_msg(func, excep_info, timeout_msg, timer.elapsed_time, timeout, expected, args, kwargs)
        ) from excep


def wait_for_exception_timeout(func, timeout_param, sentinel_exceptions, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it triggers a given exception

    :param func: callable object
    :type func: Callable
    :param timeout_param: either int in seconds or TimeoutParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when timeout_param seconds are expired else\n
                            - if TimeoutParams : timeout, timeout message and the delay between tests will be extracted from it
    :param sentinel_exceptions: The exception or list of exceptions we expect to be thrown (and which will keep on looping)
    :param args: args of callable
    :param kwargs: kwargs of callable
    """

    def wait_for_exception_timeout_unpack_exceptions(*unpacked_sentinel_exceptions):
        while True:
            try:
                func(*args, **kwargs)
            except unpacked_sentinel_exceptions:
                break
            except Exception:
                pass
            if timer.timeout_expired:
                raise TimeOutError(
                    message=get_timeout_excep_msg(
                        func,
                        "No Exception Triggered",
                        timeout_msg,
                        timer.elapsed_time,
                        timeout,
                        str(list_of_sentinel_exceptions),
                        args,
                        kwargs,
                    )
                )
            time.sleep(no_spam_sleep)

    timeout_msg, no_spam_sleep, timeout = get_timeout_params(timeout_param)
    timer = Timer(timeout)
    list_of_sentinel_exceptions = listify(sentinel_exceptions)
    wait_for_exception_timeout_unpack_exceptions(*list_of_sentinel_exceptions)


def with_timeout_until_exception(func):
    """
    Decorator to repetitively call any function until it doesn't trigger an exception anymore
    For now these decorators do not work for methods (function inside classes.
    """

    def func_wrapper(timeout_param, sentinel_exception, *args, **kwargs):
        """wrapper function with_timeout_no_exception"""
        return wait_for_exception_timeout(func, timeout_param, sentinel_exception, *args, **kwargs)

    return func_wrapper
