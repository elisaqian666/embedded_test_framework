
import logging
import pytest
import os
import re
import deprecation
from pathlib import Path
from unittest import TestCase, SkipTest
from typing import Dict

from embedded_framework.lib.logging_extras import ascii_box_render, setup_global_logging, setup_test_log_folder
from embedded_framework.lib.custom_exception import append_string_to_exception_message
from embedded_framework.lib.timeout import (
    DEFAULT_NO_SPAM_SLEEP,
    TimeOutError,
    TimeoutParams,
    wait_false_timeout,
    wait_greater_timeout,
    wait_no_exception_timeout,
    wait_not_equal_timeout,
    wait_timeout,
    wait_until_in_timeout,
)
from embedded_framework.lib.assertion import assert_equal_timeout
from embedded_framework.lib.watch import WatchError, WatchTimeParams, watch_equal, watch_false, watch_not_equal, watch_true
from embedded_framework.configurator.config_labels import LOGGERS

logger = logging.getLogger(LOGGERS.TEST_CASE)

_LOG_INITIALIZED = False
_TEST_RESULTS: dict[str, str] = {}


class _TestResultReporter:
    @pytest.hookimpl
    def pytest_runtest_logreport(self, report):
        if report.failed:
            _TEST_RESULTS[report.nodeid] = "FAILED"
        elif report.when == "call" and report.passed:
            _TEST_RESULTS.setdefault(report.nodeid, "PASSED")

    @pytest.hookimpl
    def pytest_sessionfinish(self, session, exitstatus):
        with (setup_test_log_folder() / "test-results.txt").open("w", encoding="utf-8") as stream:
            for outcome in ("PASSED", "FAILED"):
                for nodeid, result in _TEST_RESULTS.items():
                    if result == outcome:
                        stream.write(f"{outcome} {nodeid}\n")


def _register_failed_case_reporter(config: pytest.Config) -> None:
    if not config.pluginmanager.hasplugin("embedded-framework-failed-case-reporter"):
        config.pluginmanager.register(_TestResultReporter(), "embedded-framework-failed-case-reporter")


class UnittestTestCase:
    """
    This class holds everything of unittest.TestCase for us to deprecate it in future.
    """

    failureException = AssertionError

    maxDiff = None

    longMessage = True

    _diffThreshold = 2**16

    _formatMessage = TestCase._formatMessage
    _getAssertEqualityFunc = TestCase._getAssertEqualityFunc
    _baseAssertEqual = TestCase._baseAssertEqual
    _truncateMessage = TestCase._truncateMessage

    # Copy from unittest.TestCase._type_equality_funcs to avoid circular import issues when we eventually deprecate unittest.TestCase
    _type_equality_funcs = {
        dict: "assertDictEqual",
        list: "assertListEqual",
        tuple: "assertTupleEqual",
        set: "assertSetEqual",
        frozenset: "assertSetEqual",
        str: "assertMultiLineEqual",
    }

    # All assertion methods from unittest.TestCase
    assertEqual = TestCase.assertEqual
    assertNotEqual = TestCase.assertNotEqual
    assertTrue = TestCase.assertTrue
    assertFalse = TestCase.assertFalse
    assertIs = TestCase.assertIs
    assertIsNot = TestCase.assertIsNot
    assertIsNone = TestCase.assertIsNone
    assertIsNotNone = TestCase.assertIsNotNone
    assertIn = TestCase.assertIn
    assertNotIn = TestCase.assertNotIn
    assertIsInstance = TestCase.assertIsInstance
    assertNotIsInstance = TestCase.assertNotIsInstance
    assertRaises = TestCase.assertRaises
    assertRaisesRegex = TestCase.assertRaisesRegex
    assertAlmostEqual = TestCase.assertAlmostEqual
    assertGreater = TestCase.assertGreater
    assertGreaterEqual = TestCase.assertGreaterEqual
    assertLess = TestCase.assertLess
    assertLessEqual = TestCase.assertLessEqual
    assertRegex = TestCase.assertRegex
    assertNotRegex = TestCase.assertNotRegex
    assertCountEqual = TestCase.assertCountEqual
    assertMultiLineEqual = TestCase.assertMultiLineEqual
    assertSequenceEqual = TestCase.assertSequenceEqual
    assertListEqual = TestCase.assertListEqual
    assertTupleEqual = TestCase.assertTupleEqual
    assertSetEqual = TestCase.assertSetEqual
    assertDictEqual = TestCase.assertDictEqual

    pytest_request: pytest.FixtureRequest

    def __init_subclass__(cls, *args, **kwargs):
        # Initialize a fresh list per subclass to avoid shared state between subclasses
        cls._class_cleanups = []
        super().__init_subclass__(*args, **kwargs)

    @classmethod
    @pytest.fixture(scope="class", autouse=True)
    def setup_teardown_class_fixture(cls, request):
        """Simulate unittest.TestCase's setUpClass and tearDownClass using pytest fixtures"""
        setup_test_log_folder()
        _register_failed_case_reporter(request.config)
        logger.info("setup_class_fixture starting...")
        cls.pytest_request = request  # Store the request for potential use in tests
        cls.setUpClass()
        yield
        logger.info("teardown_class_fixture starting...")
        cls.tearDownClass()

        # Backward compatibility of unittest.TestCase
        cls.doClassCleanups()
        del cls.pytest_request  # Clean up the pytest_request attribute after use

    @pytest.fixture(autouse=True)
    def setup_teardown_fixture(self, get_cur_test_id):
        """Simulate unittest.TestCase's setUp and tearDown using pytest fixtures"""
        logger.info("========== TEST START: %s =========", self._test_id)
        logger.info("setup_fixture starting...")
        self.setUp()
        yield
        logger.info("teardown_fixture starting...")
        self.tearDown()

        # Backward compatibility of unittest.TestCase
        self.doCleanups()
        logger.info("=========== TEST END: %s ===========", self._test_id)

    @classmethod
    def setUpClass(cls):
        logger.debug("---------SETUPCLASS started --------------")

    def setUp(self):
        logger.debug("---------SETUP started --------------")

    def tearDown(self):
        logger.debug("---------TEARDOWN started --------------")

    @classmethod
    def tearDownClass(cls):
        logger.debug("---------TEARDOWNCLASS started --------------")

    @pytest.fixture(autouse=True)
    def get_cur_test_id(self, request: pytest.FixtureRequest):
        # test_id is like "unit_test/test_classes/test_unittest_testcase.py::TestClass1::test_no_error_without_cleanup"
        self._test_id = request.node.nodeid

    def id(self):
        # Backward compatibility of unittest.TestCase
        # self._test_id is like "unit_test/test_classes/test_unittest_testcase.py::TestClass1::test_no_error_without_cleanup"
        return self._test_id.replace(".py::", ".").replace("::", ".").replace("/", ".").replace("\\", ".")

    def addCleanup(self, function, /, *args, **kwargs):  # This name is for compatibility
        """Copied from unittest.TestCase to ensure compatibility"""
        if not hasattr(self, "_cleanups"):
            self._cleanups = []
        self._cleanups.append((function, args, kwargs))

    def doCleanups(self):
        # Backward compatibility of unittest.TestCase
        cleanups = getattr(self, "_cleanups", [])
        while cleanups:
            cleanup_func, args, kwargs = cleanups.pop()
            try:
                cleanup_func(*args, **kwargs)
            except Exception:
                logger.exception("Exception during cleanup")

    @classmethod
    def addClassCleanup(cls, func, *args, **kwargs):  # This name is for compatibility
        """Copied from unittest.TestCase to ensure compatibility"""
        cls._class_cleanups.append((func, args, kwargs))

    @classmethod
    def doClassCleanups(cls):  # This name is for compatibility
        """Copied from unittest.TestCase to ensure compatibility"""
        while cls._class_cleanups:
            class_cleanup_func, args, kwargs = cls._class_cleanups.pop()
            try:
                class_cleanup_func(*args, **kwargs)
            except Exception:
                logger.exception("Exception occurred during class cleanup: %s", class_cleanup_func)

    def skipTest(self, reason):
        raise SkipTest(reason)

    def fail(self, msg=None):
        raise self.failureException(msg)


_mpl_logger = logging.getLogger("matplotlib")
_mpl_logger.setLevel(logging.WARNING)


class BasicTestClass(UnittestTestCase):
    """
    the mother of tests using the tento framework

    .. attribute:: base_log_store_folder

        this gives the location which will contain the logs which will be stored for later evaluation
        => in this folder you can store your all files which are related to your testclass
        it will be updated by barcocollab while executing the tests

    .. attribute:: test_method_log_store_folder

        this gives the location which will contain the logs which will be stored for later evaluation
        => in this folder you can store all files which are related to your testmethod.
        it will be updated by barcocollab while executing the tests
    """

    logger = logging.getLogger(LOGGERS.TEST_CASE)

   
    dut_in_test_dict: Dict | None = None
    # overrule setup parameter: dictionary setup key, {'enable_..': False}
    overrule_settings = None
    base_log_store_folder = str(Path(__file__).resolve().parents[1] / "test_logs")
    test_class_log_store_folder = base_log_store_folder
    test_method_log_store_folder = base_log_store_folder
    test_summary_file = str(Path(base_log_store_folder) / "summary.txt")
    config_file: str

    def __init_subclass__(cls, *args, **kwargs):
        global _LOG_INITIALIZED
        if not _LOG_INITIALIZED:
            setup_global_logging(logging.INFO)
            _LOG_INITIALIZED = True
        super().__init_subclass__(*args,** kwargs)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._initialize_log_folder()
        config_file = os.getenv("TESTCONFIG") or str(
            Path(__file__).resolve().parents[1] / "system_tests" / "config" / "test_config.py"
        )
        cls.config_file = config_file
        cls._print_test_environment()
        cls.logger.info("opening %s as config file", cls.config_file)

    @classmethod
    def _initialize_log_folder(cls) -> None:
        """Create one timestamped result directory for this test process."""
        cls.base_log_store_folder = str(setup_test_log_folder())
        class_folder = Path(cls.base_log_store_folder) / re.sub(r"[^A-Za-z0-9._-]+", "_", f"{cls.__module__}.{cls.__name__}")
        class_folder.mkdir(parents=True, exist_ok=True)
        cls.test_class_log_store_folder = str(class_folder)
        cls.test_method_log_store_folder = cls.test_class_log_store_folder
        cls.test_summary_file = str(class_folder / "summary.txt")
        Path(cls.test_summary_file).touch(exist_ok=True)

    def setUp(self):
        super().setUp()
        method_folder = Path(self.test_class_log_store_folder) / re.sub(r"[^A-Za-z0-9._-]+", "_", self._test_id.rsplit("::", 1)[-1])
        method_folder.mkdir(parents=True, exist_ok=True)
        self.test_method_log_store_folder = str(method_folder)

    @classmethod
    def _print_test_environment(cls):
        tests_settings = os.getenv("TESTS_SETTINGS", "")
        ftp_location = os.getenv("FTP_LOCATION", "")
        repo_url = os.getenv("REPO_URL", "")
        commit = os.getenv("COMMIT", "")
        message = ""
        if tests_settings:
            message += f"TESTS_SETTINGS: {tests_settings}\n"

        if ftp_location:
            message += f"FTP_LOCATION: {ftp_location}\n"

        if repo_url:
            message += f"REPO_URL: {repo_url}\n"
        if commit:
            message += f"COMMIT: {commit}\n"

        if cls.config_file:
            message += f"TESTCONFIG: {cls.config_file}\n"

        to_print = ascii_box_render(message, padding=1, header="TEST ENVIRONMENT")
        cls.logger.warning(to_print)

    def assertExpectedEqualsActual(
        self, expected_value=None, actual_value=None, msg="", function_to_execute_for_info=None, *args, **kwargs
    ):
        """
        fail if the two objects are unequal as determined by the '==' operator.

        :param function_to_execute_for_info: a callable which should return a string, this will be added to the msg
        :type function_to_execute_for_info: Callable
        :param msg: a message in case of a failure
        :type msg: str
        :param actual_value: which value do we expect to be the same as the expected_value
        :param expected_value: which value do we expect to be the same as the actual_value
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            super().assertEqual(expected_value, actual_value, msg)
        except AssertionError as exc:
            separator = "=" * 70
            new_msg = f"{msg}\n{separator}\nExpected value: {expected_value}\nReceived value: {actual_value}"
            if function_to_execute_for_info:
                extra_info = function_to_execute_for_info(*args, **kwargs)
                new_msg += f"\nDebug info:{function_to_execute_for_info.__name__}(args={args}, kwargs={kwargs}) -> {extra_info} "
            new_msg += f"\n{separator}"
            append_string_to_exception_message(exc, new_msg)
            raise

    @classmethod
    @deprecation.deprecated(
        deprecated_in="1.9.0",
        removed_in="1.10.0",
        details="use 'assert_equal_timeout' from TEnTo.lib.assertion instead of this method",
    )
    def assertEqualTimeOut(
        cls, func_which_should_evaluate_to_value, value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        return assert_equal_timeout(
            func_which_should_evaluate_to_value, value, *args, timeout=timeout, msg=msg, interval=interval, **kwargs
        )

    @classmethod
    def assertNotEqualTimeOut(
        cls, func_which_should_evaluate_to_value, value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """runs a function until it returns a different value within the timeout, asserts if timeout is passed (sleeps interval of secs between each try)

        :param func_which_should_evaluate_to_value: function to execute as a function object
        :type func_which_should_evaluate_to_value: Callable
        :param value: value to which the function should evaluate to
        :param timeout: timeout as an int in seconds (though library supports timeout and  TimeOutParam(tm,msg,intv) as timeout)
        :param msg: error message as an string
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return wait_not_equal_timeout(
                func_which_should_evaluate_to_value, TimeoutParams(timeout, msg, interval), value, *args, **kwargs
            )
        except TimeOutError as err:
            raise cls.failureException(err)

    # noinspection PyIncorrectDocstring
    @classmethod
    def assertTrueTimeOut(cls, func_which_should_evaluate_to_true, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs):
        """executes a function until it returns True within timeout, asserts if timeout is passed (sleeps interval of secs between each try)

        :param func_which_should_evaluate_to_true: function to execute as a function object
        :type func_which_should_evaluate_to_true: Callable
        :param timeout: timeout as an int in seconds (though library supports timeout and  TimeOutParam(tm,msg,intv) as timeout)
        :param msg: error message as an string
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return wait_timeout(func_which_should_evaluate_to_true, TimeoutParams(timeout, msg, interval), *args, **kwargs)
        except TimeOutError as err:
            raise cls.failureException(err)

    # noinspection PyIncorrectDocstring
    @classmethod
    def assertFalseTimeOut(cls, func_which_should_evaluate_to_false, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs):
        """
        executes a function until it returns False within the timeout, asserts when timeout is passed
        (sleeps interval of seconds between each try)

        :param func_which_should_evaluate_to_false: function to execute as a function object
        :type func_which_should_evaluate_to_false: Callable
        :param timeout: timeout as an int in seconds (though library supports timeout and  TimeOutParam(tm,msg,intv) as timeout)
        :param msg: error message as an string
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return wait_false_timeout(func_which_should_evaluate_to_false, TimeoutParams(timeout, msg, interval), *args, **kwargs)
        except TimeOutError as err:
            raise cls.failureException(err)

    @classmethod
    def assertInTimeOut(
        cls, func_which_should_evaluate, sentinel_value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """
        executes a function until the sentinel value is in the return value of that function  asserts when timeout is passed

        (sleeps interval of seconds between each try)

        self.assertIn(sentinel_value, func_which_should_evaluate(), msg=timeout_params.timeout_msg)

        please refer to TEnTo.lib.timeout.wait_until_in_timeout for more details

        :param sentinel_value: this will call func until sentinel value is in the return value unless timeout is reached
        :param value: value to which the function should evaluate to
        :param func_which_should_evaluate: function to execute as a function object
        :type func_which_should_evaluate: Callable
        :param timeout: timeout as an int in seconds (though library supports timeout and TimeOutParam(tm,msg,intv) as timeout)
        :param msg: error message as an string
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return wait_until_in_timeout(func_which_should_evaluate, TimeoutParams(timeout, msg, interval), sentinel_value, *args, **kwargs)
        except TimeOutError as err:
            raise cls.failureException(err)

    @classmethod
    def assertGreaterTimeOut(
        cls, func_which_should_evaluate_to_greater, value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """executes a function until it returns a greater value within the timeout, asserts when timeout is passed (sleeps interval of seconds between each try)

        :param func_which_should_evaluate_to_greater: function to execute as a function object
        :type func_which_should_evaluate_to_greater: Callable
        :param value: value to which the function should evaluate to
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        :param timeout: timeout as an int in seconds (though library supports timeout and TimeOutParam(tm,msg,intv) as timeout)
        :param msg: the custom error message
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        """
        try:
            return wait_greater_timeout(
                func_which_should_evaluate_to_greater, TimeoutParams(timeout, msg, interval), value, *args, **kwargs
            )
        except TimeOutError as err:
            raise cls.failureException(err)

    @classmethod
    def assertNoExceptionTimeOut(
        cls, func_which_should_no_exception, sentinel_exceptions, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """executes a function until it runs without specified exception within the timeout, asserts when timeout is passed (sleeps interval of seconds between each try)

        :param func_which_should_no_exception: function to execute as a function object
        :type func_which_should_no_exception: Callable
        :param sentinel_exceptions: The exception or list of exceptions we expect to be thrown (and which will keep on looping)
        :param timeout: timeout as an int in seconds (though library supports timeout and TimeOutParam(tm,msg,intv) as timeout)
        :param msg: the custom error message
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return wait_no_exception_timeout(
                func_which_should_no_exception, TimeoutParams(timeout, msg, interval), sentinel_exceptions, *args, **kwargs
            )
        except TimeOutError as err:
            main_assertion_err = cls.failureException(err)
            if err.__cause__:
                raise main_assertion_err from err.__cause__
            raise main_assertion_err from err

    @classmethod
    def assertWatchTrueTimeOut(
        cls, func_which_should_evaluate_to_true, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """To assert a function keep returning a truthy value in a period of time

        :param func_which_should_evaluate_to_true: function to execute as a function object
        :type func_which_should_evaluate_to_true: Callable
        :param timeout: timeout as an int in seconds (though library supports timeout and TimeOutParam(tm,msg,intv) as timeout)
        :type timeout: int
        :param msg: the custom error message
        :type msg: str
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :type interval: float
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return watch_true(func_which_should_evaluate_to_true, WatchTimeParams(timeout, msg, interval), *args, **kwargs)
        except WatchError as err:
            raise cls.failureException(err)

    @classmethod
    def assertWatchFalseTimeOut(
        cls, func_which_should_evaluate_to_false, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """To assert a function keep returning a falsy value in a period of time

        :param func_which_should_evaluate_to_false: function to execute as a function object
        :type func_which_should_evaluate_to_false: Callable
        :param timeout: timeout as an int in seconds (though library supports timeout and WatchTimeParams(tm,msg,intv) as timeout)
        :type timeout: int
        :param msg: the custom error message
        :type msg: str
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :type interval: float
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return watch_false(func_which_should_evaluate_to_false, WatchTimeParams(timeout, msg, interval), *args, **kwargs)
        except WatchError as err:
            raise cls.failureException(err)

    @classmethod
    def assertWatchEqualTimeOut(
        cls, func_which_should_evaluate_to_value, sentinel_value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """To assert a function keep returning a value which equals to the sentinel value in a period of time,

        :param func_which_should_evaluate_to_value: function to execute as a function object
        :type func_which_should_evaluate_to_value: Callable
        :param sentinel_value: a value to which the function should evaluate to
        :param timeout: timeout as an int in seconds (though library supports timeout and WatchTimeParams(tm,msg,intv) as timeout)
        :type timeout: int
        :param msg: the custom error message
        :type msg: str
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :type interval: float
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return watch_equal(
                func_which_should_evaluate_to_value, WatchTimeParams(timeout, msg, interval), sentinel_value, *args, **kwargs
            )
        except WatchError as err:
            raise cls.failureException(err)

    @classmethod
    def assertWatchNotEqualTimeOut(
        cls, func_which_should_evaluate_to_value, sentinel_value, *args, timeout=0, msg=None, interval=DEFAULT_NO_SPAM_SLEEP, **kwargs
    ):
        """To assert a function keep returning a value which DOES NOT equal to the sentinel value in a period of time,

        :param func_which_should_evaluate_to_value: function to execute as a function object
        :type func_which_should_evaluate_to_value: Callable
        :param sentinel_value: a value to which the function should NOT evaluate to
        :param timeout: timeout as an int in seconds (though library supports timeout and  WatchTimeParams(tm,msg,intv) as timeout)
        :type timeout: int
        :param msg: the custom error message
        :type msg: str
        :param interval: number of seconds as a float to sleep between each try defaults to DEFAULT_NO_SPAM_SLEEP
        :type interval: float
        :param args: extra arguments needed for the function to run
        :param kwargs: extra keyword arguments needed for the function to run
        """
        try:
            return watch_not_equal(
                func_which_should_evaluate_to_value, WatchTimeParams(timeout, msg, interval), sentinel_value, *args, **kwargs
            )
        except WatchError as err:
            raise cls.failureException(err)
