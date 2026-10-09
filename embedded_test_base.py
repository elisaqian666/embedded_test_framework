"""Purpose: Provide a reusable unittest base class for embedded system tests."""

import importlib.util
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from embedded_test_framework.basic_test_setup import BasicTestClass, register_test_context
from embedded_test_framework.configurator.config_labels import LOGGERS
from embedded_test_framework.devices import Capability
from embedded_test_framework.devices.linux.linux_device import LinuxDevice
from embedded_test_framework.helpers.he_coredump import CoreDumpHelper
from embedded_test_framework.helpers.he_host_pc import SystemHelper
from embedded_test_framework.runtime import Runtime


class EmbeddedTestCase(BasicTestClass):
    """Purpose: Initialize one configured DUT for a system-test subclass."""

    config: Mapping[str, object] | None = None
    dut_name: str | None = None
    dut_names: Sequence[str] | None = None
    runtime: Runtime
    logger: logging.Logger
    required_capabilities: tuple[Capability, ...] = ()
    engine_name: str | None = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.test_zzzz_check_for_crashes = cls._check_for_crashes

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        SystemHelper.check_folder(cls.base_log_store_folder)
        cls.logger = logging.getLogger(LOGGERS.TEST_CASE)
        cls.logger.setLevel(logging.INFO)
        cls.logger.propagate = True
        config = dict(cls.config) if cls.config else cls._load_config(Path(cls.config_file))
        names = tuple(cls.dut_names or (() if cls.dut_name is None else (cls.dut_name,)))
        register_test_context(cls.pytest_request.node.nodeid, names)
        if not names and not config.get("osciiloscope", {}).get("enable"):
            raise RuntimeError("Set dut_name or dut_names, or enable an oscilloscope")
        devices = config.get("devices")
        if not isinstance(devices, Mapping) or any(name not in devices for name in names):
            raise RuntimeError("Every requested DUT must be defined in the test configuration")
        config["devices"] = {name: devices[name] for name in names}
        cls.runtime = Runtime.from_mapping(config, source=cls.config_file)
        cls.pytest_request.addfinalizer(cls.runtime.close)
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

    def _check_for_crashes(self) -> None:
        """Collect Linux coredumps and fail the inherited crash check when any exist."""
        files = self._collect_linux_coredumps(Path(self.test_method_log_store_folder) / "coredumps")
        self.assertFalse(files, f"Coredumps detected: {', '.join(map(str, files))}")

    @classmethod
    def _collect_linux_coredumps(cls, destination: Path) -> list[Path]:
        """Collect Linux crash files into the current test's artifact directory."""
        collected: list[Path] = []
        for name, dut in cls.duts.items():
            if not isinstance(dut, LinuxDevice):
                continue
            connection = next((key for key, value in dut.config.connections.items() if value.protocol == "ssh"), None)
            if connection is None:
                cls.logger.warning("Skipping coredump collection for %s: no SSH connection", name)
                continue
            paths = dut.config.metadata.get("coredump_paths", CoreDumpHelper.DEFAULT_PATHS)
            if not isinstance(paths, (list, tuple)) or not all(isinstance(path, str) and path for path in paths):
                cls.logger.warning("Ignoring invalid coredump_paths for %s", name)
                continue
            try:
                helper = CoreDumpHelper(
                    lambda command, timeout: dut.execute(command, timeout, connection=connection, check=False), tuple(paths)
                )
                files = helper.collect(destination / name, dut.engine(connection).get_files)
                if files:
                    cls.logger.warning("Collected coredumps for %s: %s", name, ", ".join(map(str, files)))
                    collected.extend(files)
            except Exception:  # noqa: BLE001 - artifact collection must not hide the original test result
                cls.logger.error("Unable to collect coredumps for %s", name)
        return collected
