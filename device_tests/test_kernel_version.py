"""Hardware example using the common device test lifecycle."""
from pathlib import Path

from embedded_test_framework.testing import DeviceTestBase


class TestKernelVersion(DeviceTestBase):
    config_path = Path(__file__).with_name("devices.json")
    device_name = "linux-board"
    required_environment = ("DUT_SSH_PASSWORD",)

    def test_kernel_version(self):
        # given: A Linux device connected over SSH by DeviceTestBase.
        self.logger.info("Checking kernel version on %s", self.device_info["metadata"]["address"])

        # when: Query the running kernel version.
        result = self.device.execute("uname -r", timeout=10)

        # then: The command succeeds and returns a nonempty kernel version.
        assert result.exit_code == 0, f"uname -r failed: {result.stderr}"
        kernel_version = result.stdout.strip()
        assert kernel_version, "uname -r returned an empty kernel version"
        self.logger.info("Kernel version: %s", kernel_version)
