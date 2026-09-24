"""Purpose: Provide a reusable unittest base class for embedded system tests."""

import importlib.util
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from embedded_framework.basic_test_setup import BasicTestClass
from embedded_framework.configurator.config_labels import LOGGERS
from embedded_framework.devices import Capability
from embedded_framework.helpers.he_host_pc import SystemHelper
from embedded_framework.lib import assertion
from embedded_framework.runtime import Runtime


class EmbeddedTestCase(BasicTestClass):
    """Purpose: Initialize one configured DUT for a system-test subclass."""

    config: Mapping[str, object] | None = None
    dut_name: str | None = None
    dut_names: Sequence[str] | None = None
    runtime: Runtime
    logger: logging.Logger
    required_capabilities: tuple[Capability, ...] = ()
    engine_name: str | None = None

    def assertEqual(self, first: object, second: object, msg: str | None = None) -> None:  # noqa: N802 - unittest API
        """Purpose: Compare values through the framework assertion layer."""
        assertion.assert_equal(first, second, msg)

    def assertTrue(self, expr: object, msg: str | None = None) -> None:  # noqa: N802 - unittest API
        """Purpose: Check truth through the framework assertion layer."""
        assertion.assert_true(expr, msg)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        SystemHelper.check_folder(cls.base_log_store_folder)
        cls.logger = logging.getLogger(LOGGERS.TEST_CASE)
        cls.logger.setLevel(logging.INFO)
        cls.logger.propagate = True
        config = dict(cls.config) if cls.config else cls._load_config(Path(cls.config_file))
        names = tuple(cls.dut_names or (() if cls.dut_name is None else (cls.dut_name,)))
        if not names and not config.get("osciiloscope", {}).get("enable"):
            raise RuntimeError("Set dut_name or dut_names, or enable an oscilloscope")
        devices = config.get("devices")
        if not isinstance(devices, Mapping) or any(name not in devices for name in names):
            raise RuntimeError("Every requested DUT must be defined in the test configuration")
        config["devices"] = {name: devices[name] for name in names}
        cls.runtime = Runtime.from_mapping(config, source=cls.config_file)
        cls.runtime.connect()
        cls.duts = cls.runtime.duts
        if names:
            cls.dut = cls.duts[names[0]]
            for capability in cls.required_capabilities:
                if not cls.dut.supports(capability):
                    raise RuntimeError(f"DUT {cls.dut.name} does not support {capability}")
            cls.engine = cls.dut.engine(cls.engine_name)
        cls.oscilloscope = cls.runtime.oscilloscope

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        spec = importlib.util.spec_from_file_location("system_test_config", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load test configuration: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = getattr(module, "config", None)
        if not isinstance(config, dict):
            raise RuntimeError(f"Test configuration must define a dict named config: {path}")
        return config

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.runtime.close()
        finally:
            super().tearDownClass()
