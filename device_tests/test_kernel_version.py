"""Explicit hardware test; excluded from the default unittest suite."""
import os

import pytest

from embedded_test_framework import Device
from embedded_test_framework.engine import SSHTransport


def test_kernel_version():
    password = os.environ.get("DUT_SSH_PASSWORD")
    if not password:
        pytest.skip("Set DUT_SSH_PASSWORD to run the real-device test")

    ssh = SSHTransport(
        host="192.168.1.103",
        username="root",
        password=password,
        timeout=10,
    )
    with Device("linux-board", {"shell": ssh}) as device:
        result = device.execute("uname -r", timeout=10)
        assert result.exit_code == 0, f"uname -r failed: {result.stderr}"
        kernel_version = result.stdout.strip()
        assert kernel_version, "uname -r returned an empty kernel version"
        print(f"Kernel version: {kernel_version}")
