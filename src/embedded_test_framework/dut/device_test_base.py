"""Common pytest xunit lifecycle; override product hooks, not runner hooks."""
import os
from pathlib import Path

from ..configurators import Registry, ConfigurationUnderTest
from ..libs.errors import ConfigurationError
from ..libs.logging import configure_logging, get_logger


class DeviceTestBase:
    config_path = None
    device_name = "dut"
    required_environment = ()

    @classmethod
    def build_registry(cls):
        return Registry.defaults()

    @classmethod
    def setup_class(cls):
        cls.device = None
        cls.cut = None
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
            cls.cut = ConfigurationUnderTest(cls.config_file, device_name=cls.device_name, registry=cls.build_registry())
            cls.device = cls.cut.device
            cls.device_info = {"name": cls.device.name, "metadata": dict(cls.device.metadata)}
            cls.logger.info("Test class initialized")
            cls.setupclass()
        except BaseException as exc:
            cls._cleanup_after_failure(exc)
            raise

    @classmethod
    def _cleanup_after_failure(cls, original):
        if cls.cut is not None:
            try:
                cls.cut.close()
            except Exception as cleanup:
                original.add_note(f"Device cleanup failed: {type(cleanup).__name__}")

    def setup_method(self, method):
        try:
            self.cut.prepare()
            self.logger.info("Test setup: %s", method.__name__)
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
            self.cut.close()
            self.logger.info("Test teardown: %s", method.__name__)

    @classmethod
    def teardown_class(cls):
        try:
            cls.teardownclass()
        except BaseException as exc:
            cls._cleanup_after_failure(exc)
            raise
        else:
            if cls.cut is not None:
                cls.cut.close()
        finally:
            cls.device = None
            cls.cut = None

    @classmethod
    def setupclass(cls):
        """Class preparation after configuration; device is not connected yet."""

    def setup(self):
        """Per-test preparation after connecting the device."""

    def teardown(self):
        """Per-test cleanup before closing the device."""

    @classmethod
    def teardownclass(cls):
        """Class cleanup; do not assume the device is connected."""
