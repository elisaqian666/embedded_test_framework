"""Multi-device lifecycle with the same product hook names as DeviceTestBase."""
from pathlib import Path

from .device_test_base import DeviceTestBase
from ..configurators.runtime import TestContext
from ..configurators import ConfigurationUnderTest
from ..libs.errors import ConfigurationError
from ..libs.logging import configure_logging, get_logger


class EmbeddedTestCase(DeviceTestBase):
    """Use the opt-in pytest plugin for automatic evidence on test assertion failures."""
    runtime_overrides = None

    @classmethod
    def setup_class(cls):
        import os
        cls.context = None
        cls.cut = None
        cls.device = None
        cls.device_info = {}
        configure_logging()
        cls.logger = get_logger("dut", cls.device_name)
        missing = [name for name in cls.required_environment if not os.environ.get(name)]
        if missing:
            import pytest
            pytest.skip("Set required environment variables: " + ", ".join(missing))
        if cls.config_path is None:
            raise ConfigurationError("Define config_path on the test class")
        cls.config_file = Path(cls.config_path).expanduser().resolve()
        try:
            cls.cut = ConfigurationUnderTest(cls.config_file, registry=cls.build_registry(),
                                              device_name=cls.device_name, overrides=cls.runtime_overrides)
            cls.context = cls.cut
            if cls.device_name not in cls.context.devices:
                raise ConfigurationError("device_name must identify a configured device")
            cls.device = cls.context.devices[cls.device_name]
            cls.device_info = {"name": cls.device.name, "metadata": dict(cls.device.metadata)}
            cls.setupclass()
        except BaseException as exc:
            cls._cleanup_after_failure(exc)
            raise

    @classmethod
    def _cleanup_after_failure(cls, original):
        if cls.context is not None:
            try:
                cls.context.collect_evidence()
            except Exception as diagnostic:
                original.add_note(f"Evidence collection failed: {type(diagnostic).__name__}")
            try:
                cls.context.close()
            except Exception as cleanup:
                original.add_note(f"Runtime cleanup failed: {type(cleanup).__name__}")

    def setup_method(self, method):
        try:
            self.context.prepare()
            self.setup()
        except BaseException as exc:
            self._cleanup_after_failure(exc)
            raise

    def teardown_method(self, method):
        try:
            self.teardown()
        except BaseException as exc:
            self._cleanup_after_failure(exc)
            raise
        else:
            self.context.close()

    @classmethod
    def teardown_class(cls):
        try:
            cls.teardownclass()
        except BaseException as exc:
            cls._cleanup_after_failure(exc)
            raise
        else:
            if cls.context is not None:
                cls.context.close()
        finally:
            cls.context = None
            cls.cut = None
            cls.device = None
