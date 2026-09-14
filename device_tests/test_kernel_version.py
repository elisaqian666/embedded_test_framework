"""Hardware example using the common device test lifecycle."""
from pathlib import Path

from embedded_test_framework.dut import DeviceTestBase
import os

class TestKernelVersion(DeviceTestBase):
    config_path = Path(__file__).resolve().parents[1] / "configs" / "testconfig.py"
    device_name = "linux-board"
    required_environment = ("DUT_SSH_PASSWORD",)

    @classmethod
    def setup_class(cls):
        os.environ["DUT_SSH_PASSWORD"] = "letmein"
        super().setup_class()

    def test_kernel_version(self):
        # given: A Linux device connected over SSH by DeviceTestBase.
        self.logger.info("Checking kernel version on %s", self.device_info["metadata"]["address"])

        # when: Query the running kernel version.
        result = self.cut.engines.shell.execute("uname -r", timeout=10)

        # then: The command succeeds and returns a nonempty kernel version.
        assert result.exit_code == 0, f"uname -r failed: {result.stderr}"
        kernel_version = result.stdout.strip()
        assert kernel_version, "uname -r returned an empty kernel version"
        self.logger.info("Kernel version: %s", kernel_version)

    # def test_device_reboot(self):
    #     # given: A Linux device connected over SSH by DeviceTestBase.
    #     self.logger.info("Start to reboot device %s", self.device_info["metadata"]["address"])

    #     # when: Reboot the device.
    #     # result = self.device.reboot()

    #     # then: The command succeeds and returns a nonempty kernel version.
    #     wait_time = 150  # seconds
    #     self.logger.info("Waiting for device to reboot for %d seconds...", wait_time)
    #     # self.device.wait_for_reboot(timeout=wait_time)
    #     # # self.device.health_check()
    #     assert result.exit_code == 0, f"uname -r failed: {result.stderr}"
    #     kernel_version = result.stdout.strip()
    #     assert kernel_version, "uname -r returned an empty kernel version"
    #     self.logger.info("Kernel version: %s", kernel_version)
