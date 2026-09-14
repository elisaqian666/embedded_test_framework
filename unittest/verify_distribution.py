"""Install a wheel into a temporary directory and exercise it outside the source tree.

Run with: python -I unittest/verify_distribution.py dist/package.whl
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def verify(wheel):
    wheel = Path(wheel).resolve()
    with zipfile.ZipFile(wheel) as archive:
        files = set(archive.namelist())
    required = {
        "configurators/configurator_under_test.py", "dut/device_test_base.py",
        "engine/he_commands.py", "helpers/helper_base.py", "hosts/local.py",
        "libs/assertions.py", "libs/watch.py", "libs/timeout.py",
    }
    for name in required:
        if "embedded_test_framework/" + name not in files:
            raise RuntimeError(f"Wheel is missing {name}")
    forbidden = ("adapters/", "capabilities/", "diagnostics/", "testing/", "core/", "services/", "lab/", "wait/")
    if any(name.startswith("embedded_test_framework/" + prefix) for name in files for prefix in forbidden):
        raise RuntimeError("Wheel contains a removed package")
    with tempfile.TemporaryDirectory(prefix="embedded-wheel-") as temporary:
        root = Path(temporary)
        target = root / "installed"
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps",
                        "--target", str(target), str(wheel)], check=True, stdin=subprocess.DEVNULL)
        config = root / "testconfig.py"
        config.write_text('TEST_CONFIG = {"devices": {"dut": {"channels": {"shell": {"type": "memory", "responses": {"uname -r": "6.6.1"}}}}}}', encoding="utf-8")
        consumer = root / "consumer.py"
        consumer.write_text('''
import pathlib
import pkgutil
import importlib
import sys
sys.path.insert(0, sys.argv[1])
import embedded_test_framework as sdk
assert pathlib.Path(sdk.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
for module in pkgutil.walk_packages(sdk.__path__, sdk.__name__ + "."):
    importlib.import_module(module.name)
from embedded_test_framework.dut import DeviceTestBase
from embedded_test_framework.libs import Assertions, is_ipv4
with sdk.ConfigurationUnderTest("testconfig.py") as cut:
    Assertions.assert_equal(cut.helpers.linux.kernel_version(), "6.6.1")
    Assertions.assert_true(is_ipv4("192.168.1.103"))
print("Installed wheel: all modules imported and cut workflow passed")
''', encoding="utf-8")
        subprocess.run([sys.executable, "-I", str(consumer), str(target)], cwd=root,
                       check=True, stdin=subprocess.DEVNULL)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_distribution.py path/to/package.whl")
    verify(sys.argv[1])
