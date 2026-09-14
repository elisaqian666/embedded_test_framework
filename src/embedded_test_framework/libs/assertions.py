"""Assertions remain active even when Python runs with -O."""
from contextlib import contextmanager


class Assertions:
    @staticmethod
    def assert_true(value, message="Expected a truthy value"):
        if not value:
            raise AssertionError(message)

    @staticmethod
    def assert_false(value, message="Expected a falsy value"):
        if value:
            raise AssertionError(message)

    @staticmethod
    def assert_equal(actual, expected, message=None):
        if actual != expected:
            raise AssertionError(message or f"Expected {expected!r}, got {actual!r}")

    @staticmethod
    def assert_not_equal(actual, unexpected, message=None):
        if actual == unexpected:
            raise AssertionError(message or f"Did not expect {unexpected!r}")

    @staticmethod
    def assert_in(member, container, message=None):
        if member not in container:
            raise AssertionError(message or f"{member!r} not found in container")

    @staticmethod
    def assert_not_none(value, message="Expected a non-None value"):
        if value is None:
            raise AssertionError(message)

    @staticmethod
    @contextmanager
    def assert_raises(exception_type):
        try:
            yield
        except exception_type:
            return
        raise AssertionError(f"Expected {exception_type.__name__} to be raised")
