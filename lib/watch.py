"""Purpose: Poll values until a condition is met."""

import logging
import time
from collections import namedtuple

from embedded_framework.lib.basic_helper_functions import get_parent_that_defined_method
from embedded_framework.lib.custom_exception import EmbeddedFrameworkException
from embedded_framework.lib.timer import Timer

DEFAULT_WATCH_TIME = 0
DEFAULT_FAIL_MSG = None
DEFAULT_NO_SPAM_SLEEP = 0.15
WatchTimeParams = namedtuple("WatchTimeParams", ["watch_time", "watch_fail_msg", "no_spam_sleep"])
WatchTimeParams.__new__.__defaults__ = (DEFAULT_WATCH_TIME, DEFAULT_FAIL_MSG, DEFAULT_NO_SPAM_SLEEP)

logger = logging.getLogger("watch")


class WatchError(EmbeddedFrameworkException):
    """A polling error raised by framework operations."""

    def __init__(self, message=""):
        super().__init__(message)
        self.message = message

    def __repr__(self):
        return self.message


def get_watchtime_params(watchtime_param):
    """
    Gets the parameters from watchtime_params.  This is either number indicating the timeout for the watch function or holds more
    information such a the delay between consecutive tests and the specific failure message replacing the standard one.

    :param watchtime_param: Either just a number or an instance of WatchTimeParams.
    :return: (watch_fail_msg, no_spam_sleep, watch_time)
    """
    if isinstance(watchtime_param, WatchTimeParams):
        watch_time = watchtime_param.watch_time
        watch_fail_msg = watchtime_param.watch_fail_msg
        no_spam_sleep = watchtime_param.no_spam_sleep
    else:
        watch_time = watchtime_param
        watch_fail_msg = None
        no_spam_sleep = DEFAULT_NO_SPAM_SLEEP
    return watch_fail_msg, no_spam_sleep, watch_time


def get_timeout_excep_msg(func, ret_val, msg, stopwatch: Timer, expected):
    if msg:
        return msg
    parent_object = get_parent_that_defined_method(func)
    format_str = "Failed after %f seconds (out of %f), executing function '%s()',\nExpecting '%s' but on the last call it returned '%s'."
    return format_str % (stopwatch.elapsed_time, stopwatch.watch_time, ".".join((parent_object, func.__name__)), expected, ret_val)


def __debug_logging(func, ret_val):
    return logger.debug('Called: "{}()", return value: {}'.format(func.__name__, ret_val))


def watch_true(func, watchtime_param, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns a value that would evaluate to True by bool() or timeout is reached

    :param func: callable object
    :param watchtime_param: either int in seconds or WatchTimeParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else\n
                            - if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    watch_fail_msg, no_spam_sleep, watch_time = get_watchtime_params(watchtime_param)
    timer = Timer(watch_time)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if not ret_val:  # Will raise an exception on not None, False, empty
            expected = "bool(%s()) to be True" % (".".join((get_parent_that_defined_method(func), func.__name__)))
            raise WatchError(message=get_timeout_excep_msg(func, ret_val, watch_fail_msg, timer, expected))
        if timer.timeout_expired:
            return ret_val
        time.sleep(no_spam_sleep)


def with_watch_true(func):
    """
    Decorator to repetitively call any function until it returns a value that would evaluate to True by bool() or timeout is reached
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(watchtime_param, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns a value that would evaluate to True by bool() or timeout is reached.
        It steals the first argument, the rest is passed to the function being wrapped.

        :param watchtime_param: either int in seconds or WatchTimeParams named tuple :
            if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else
            if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return watch_true(func, watchtime_param, *args, **kwargs)

    return func_wrapper


def watch_false(func, watchtime_param, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns a value that would evaluate to False by bool() or timeout is reached

    :param func: callable object
    :param watchtime_param: either int in seconds or WatchTimeParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else\n
                            - if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    watch_fail_msg, no_spam_sleep, watch_time = get_watchtime_params(watchtime_param)
    expected = "bool(%s()) to be False" % (".".join((get_parent_that_defined_method(func), func.__name__)))
    timer = Timer(watch_time)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val:  # Will raise an exception on None, False, empty
            raise WatchError(message=get_timeout_excep_msg(func, ret_val, watch_fail_msg, timer, expected))
        if timer.timeout_expired:
            return ret_val
        time.sleep(no_spam_sleep)


def with_watch_false(func):
    """
    Decorator to repetitively call any function until it returns a value that would evaluate to False by bool() or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(watchtime_param, *args, **kwargs):
        """
        Wrapper to repetitively call any function until:
        - it returns a value that would evaluate to False by bool()
        - the timeout is reached.
        It steals the first argument, the rest is passed to the function being wrapped.

        :param watchtime_param: either int in seconds or WatchTimeParams named tuple :
            if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else
            if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return watch_false(func, watchtime_param, *args, **kwargs)

    return func_wrapper


def watch_equal(func, watchtime_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function, until it returns a value that differs from the desired value or timeout is reached.

    If the return value of func differs from the sentinel value before watchtime expires, a WatchError is raised.

    :param func: callable object.
    :param sentinel_value: this will call func until the return value != sentinel_value or until timeout is reached.
    :param watchtime_param: either int in seconds or WatchTimeParams named tuple:

        - if int : check the condition until watchtime_param seconds are expired.
        - if WatchTimeParams : watchtime, fail message and the delay between tests will be extracted from it.

    :raises WatchError: if the function returns a value that differs from the sentinel value.
    :return: the return value of the last call of func.
    """
    watch_fail_msg, no_spam_sleep, watch_time = get_watchtime_params(watchtime_param)
    expected = "%s() == '%s'" % (".".join((get_parent_that_defined_method(func), func.__name__)), str(sentinel_value))

    timer = Timer(watch_time)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val != sentinel_value:
            raise WatchError(message=get_timeout_excep_msg(func, ret_val, watch_fail_msg, timer, expected))
        if timer.timeout_expired:
            return ret_val
        time.sleep(no_spam_sleep)


def with_watch_equal(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(watchtime_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until sentinel value is received or timeout
        :param watchtime_param: either int in seconds or WatchTimeParams named tuple :
            if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else
            if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return watch_equal(func, watchtime_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper


def watch_not_equal(func, watchtime_param, sentinel_value, *args, **kwargs):
    """
    Wrapper to repetitively call any function until it returns the desired value or timeout is reached

    :param func: callable object
    :param sentinel_value: this will call func until the return value != sentinel_value unless timeout is reached
    :param watchtime_param: either int in seconds or WatchTimeParams named tuple:\n
                            - if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else\n
                            - if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
    """
    watch_fail_msg, no_spam_sleep, watch_time = get_watchtime_params(watchtime_param)
    expected = "%s() != '%s'" % (".".join((get_parent_that_defined_method(func), func.__name__)), str(sentinel_value))
    timer = Timer(watch_time)
    while True:
        ret_val = func(*args, **kwargs)
        __debug_logging(func, ret_val)
        if ret_val == sentinel_value:
            raise WatchError(message=get_timeout_excep_msg(func, ret_val, watch_fail_msg, timer, expected))
        if timer.timeout_expired:
            return ret_val
        time.sleep(no_spam_sleep)


def with_watch_not_equal(func):
    """
    Decorator to repetitively call any function until it returns the desired value or timeout is reached.
    For now these decorators do not work for methods (function inside classes.

    :param func: callable object
    """

    def func_wrapper(watchtime_param, wrapper_sentinel_value, *args, **kwargs):
        """
        Wrapper to repetitively call any function until it returns the desired value or timeout is reached. It steals the first two
        arguments, the rest is passed to the function being wrapped.

        :param wrapper_sentinel_value: Loop until received value differs from sentinel value or timeout
        :param watchtime_param: either int in seconds or WatchTimeParams named tuple :
            if int : a TimeOutError exception will be raised when watchtime_param seconds are expired else
            if WatchTimeParams : timeout, timeout message and the delay between tests will be extracted from it
        """
        return watch_not_equal(func, watchtime_param, wrapper_sentinel_value, *args, **kwargs)

    return func_wrapper
