"""Purpose: Provide a reusable unittest base class for embedded system tests."""

from collections.abc import Mapping
import logging
from pathlib import Path
from unittest import TestCase

from embedded_framework.lib import assertion
from embedded_framework.runtime import Runtime, initialize_from_mapping


class EmbeddedTestCase(TestCase):
    """Purpose: Initialize one configured DUT for a system-test subclass."""

    config: Mapping[str, object]
    dut_name: str
    runtime: Runtime
    logger: logging.Logger

    def assertEqual(self, first: object, second: object, msg: str | None = None) -> None:  # noqa: N802 - unittest API
        """Purpose: Compare values through the framework assertion layer."""
        assertion.assert_equal(first, second, msg)

    def assertTrue(self, expr: object, msg: str | None = None) -> None:  # noqa: N802 - unittest API
        """Purpose: Check truth through the framework assertion layer."""
        assertion.assert_true(expr, msg)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.logger = logging.getLogger("test_case")
        if not getattr(cls, "config", None) or not getattr(cls, "dut_name", None):
            raise RuntimeError("Set config and dut_name on the system-test subclass")
        cls.runtime = initialize_from_mapping(dict(cls.config), source=Path(__file__), connect=True)
        cls.dut = cls.runtime.duts[cls.dut_name]

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.runtime.close()
        finally:
            super().tearDownClass()
