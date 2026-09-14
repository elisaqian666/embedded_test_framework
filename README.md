# Embedded Test Framework

Python 3.11+ SDK for embedded-device tests maintained in a separate repository. The layout follows the test-class -> ConfigurationUnderTest (`cut`) -> engines/helpers/features/DUT relationship. Product-specific workflows and assertions remain in test subclasses or external extensions.

## Directory structure

```text
src/embedded_test_framework/
  configurators/
    configurator_under_test.py  ConfigurationUnderTest and named resource views
    testconfig_loader.py       Trusted Python testconfig.py loading
    inventory.py               Registry, device factory, JSON compatibility
    runtime.py                 Multi-device configuration and resource composition
  dut/
    device_base.py             Device interface, channel routing and lifecycle
    device_test_base.py        Common single-device pytest test class
    context_test_base.py       Multi-device test class
    linux_device.py            Linux network/reboot implementations
    device_features.py         Extension contracts for device features
    services/                  System, network, health, file and device workflows
  engine/                      SSH, ADB, serial, HTTP, FTP and memory engines
  helpers/                     Linux commands, Valgrind, QR, build, artifacts,
                               evidence and instrument extension contracts
  hosts/                       Local host, applications, peripherals, driver status
  libs/                        Assertions, address/platform predicates, logging,
                               deadline/watch utilities, contracts and cleanup
  tools/                       Reserved; currently empty
configs/testconfig.py          Hardware configuration example
examples/external_tests/       Offline fixture-based consumer examples
examples/runtime_tests/        Offline multi-device examples
unittest/                     Framework tests
Jenkinsfile                   Test, package and archive pipeline
```

There are no top-level `adapters`, `capabilities`, `diagnostics`, `testing`, `core`, or `services` packages. Their active implementations have been moved into the directories above. Protocol-level interfaces still exist in `libs/contracts.py`, and device feature contracts live in `dut/device_features.py`.

## Install

From the framework repository:

```powershell
python -m pip install -e ".[test,ssh]"
```

Or install it by path from an independent test repository:

```powershell
python -m pip install -e "D:/work_project/embedded_test_framework[test,ssh]"
```

Optional extras are `ssh` (Paramiko password sessions), `serial` (pyserial), `host` (serial and process enumeration), `qr` (QR PNG generation), and `test` (pytest). OpenSSH and ADB require their executables on the host. ADB also accepts an explicit executable path. Core imports do not require optional packages.

## ConfigurationUnderTest: the test entry point

`ConfigurationUnderTest` reads configuration, constructs resources without hardware I/O, and owns their lifecycle. Each view references the same objects; accessing an engine through `cut` does not create another connection.

| Entry point | Meaning |
| --- | --- |
| `cut.device` / `cut.dut` | Selected test device |
| `cut.devices["peer"]` | Another configured device |
| `cut.engines.shell` | Selected device's configured shell engine |
| `cut.engines.console` | Serial engine, if configured |
| `cut.engines.adb` | ADB engine, if configured |
| `cut.engines.files` | FTP engine, if configured |
| `cut.helpers.linux` | Linux command helper for the selected device |
| `cut.helpers.host` / `cut.host` | The selected device's host |
| `cut.helpers.build` | Explicit host build commands |
| `cut.helpers.artifacts` | Local file copy and SHA-256 operations |
| `cut.helpers.valgrind` | Explicit Valgrind runs on the selected device |
| `cut.features` | Registered device features; no fabricated product behavior |
| `cut.services` | Configured device workflows |

Collections support both `collection.name` and `collection["name"]`. Use bracket access for names that conflict with mapping methods, such as `items`. Call `cut.prepare()` before engine operations and `cut.close()` afterward, or use a context manager. Engine operations enforce their connected state. Constructors do not probe hardware.

```python
from embedded_test_framework import ConfigurationUnderTest
from embedded_test_framework.libs import Assertions

with ConfigurationUnderTest("testconfig.py", device_name="dut") as cut:
    result = cut.engines.shell.execute("uname -r", timeout=10)
    result.check()
    Assertions.assert_true(result.stdout.strip(), "Kernel version must not be empty")
```

## testconfig.py

Python configuration is executable code: load only trusted files from your test repository. It is executed without adding its directory to `sys.path`. `${NAME}` references resolve from environment variables after loading, and missing variables raise configuration errors.

```python
DEVICE_NAME = "dut"
DEVICE_TYPE = "generic"
METADATA = {"address": "192.168.1.103", "platform": "Linux"}
LOGGING = {"level": "info", "levels": {"engine": "debug", "host": "warning"}}
HOST = {"type": "local", "name": "bench-pc"}
SSH = {"host": "192.168.1.103", "port": 22, "username": "root",
       "password": "${DUT_SSH_PASSWORD}", "timeout": 10}
SERIAL = None  # {"port": "COM3", "baudrate": 115200, "timeout": 3}
ADB = None     # {"executable": "C:/Android/adb.exe", "device": "board-1"}
FTP = None     # {"host": "192.168.1.103", "port": 21,
               #  "remote_path": "/image.bin", "local_path": "downloads/image.bin"}
```

Omitted or `None` protocol sections are disabled. SSH, SERIAL, ADB and FTP map to `shell`, `console`, `adb` and `files`. FTP paths are stored in `cut.device.metadata["ftp_paths"]`; relative local paths resolve against the configuration directory. A path alone does not trigger a transfer.

For multi-device setups, custom engines, HTTP or memory channels, define `TEST_CONFIG = {...}` using the inventory structure from `examples/runtime_tests/devices.json`. `TEST_CONFIG` takes precedence over individual settings. Optional `HELPERS`, `SERVICES`, `INPUTS` and `ARTIFACTS` settings configure registered helpers/workflows and runtime options when using protocol sections.

Existing JSON configuration remains supported. `load_device(path, name)` is the lightweight single-device API; use `ConfigurationUnderTest` for helper and multi-device ownership. `ConfigurationUnderTest.create_device(name)` returns the already constructed device rather than creating a second instance.

## Reusable test class

```python
from pathlib import Path
from embedded_test_framework.dut import DeviceTestBase

class TestKernelVersion(DeviceTestBase):
    config_path = Path(__file__).with_name("testconfig.py")
    device_name = "dut"
    required_environment = ("DUT_SSH_PASSWORD",)

    def test_kernel_version(self):
        # given: The common test base has prepared cut and connected the DUT.
        self.logger.info("Checking kernel version")
        # when: Query the kernel.
        result = self.cut.engines.shell.execute("uname -r", timeout=10)
        # then: The command succeeds and returns a version.
        assert result.exit_code == 0
        assert result.stdout.strip()
```

| pytest callback | Framework behavior | Product hook |
| --- | --- | --- |
| `setup_class` | Load configuration/logging, create cut and device metadata | `setupclass` (classmethod) |
| `setup_method` | Prepare helpers and connect devices | `setup` |
| `teardown_method` | Run product cleanup, then release resources | `teardown` |
| `teardown_class` | Run class cleanup, close remaining host resources, clear references | `teardownclass` (classmethod) |

Override the product hooks rather than pytest's callbacks. `self.device`, `self.device_info` and `self.logger` remain available. `EmbeddedTestCase` additionally exposes `self.context`, pointing to the same `cut`, for multi-device tests and evidence collection. Class hooks must not assume the device is connected. Setup failures roll resources back; cleanup does not replace the original exception.

## Helpers, hosts and features

```python
from embedded_test_framework.helpers import LinuxCommandHelper, ArtifactHelper
from embedded_test_framework.libs import Assertions, is_linux, is_ipv4, is_mac_address
from embedded_test_framework.libs.timeout import Deadline
from embedded_test_framework.libs import watch

Assertions.assert_true(is_ipv4("192.168.1.103"))
Assertions.assert_true(is_mac_address("AA:BB:CC:DD:EE:FF"))
# With an already connected device:
# version = LinuxCommandHelper(device).kernel_version()
# digest = ArtifactHelper.sha256("firmware.bin")
```

`Assertions` provides truthiness, equality/inequality, membership, non-None and expected-exception checks, including under Python `-O`. Predicates include `is_linux`, `is_windows`, `is_mac`, `is_ipv4`, `is_ipv6` and `is_mac_address`. MAC validation accepts six hexadecimal octets with consistent colon or hyphen separators.

`libs.watch` provides `until_true`, `until_false`, `until_equal`, `until_no_exception`, `stays_true` and `stays_equal`. Retry exceptions must be selected explicitly. `Deadline` is a cooperative monotonic budget: pass its remaining time to I/O calls. It does not forcibly stop functions or threads.

`Helper` defines repeatable `prepare`/`cleanup` hooks for external instruments. `PowerSwitcher`, `USBSwitcher` and `DisplayCapture` are extension contracts; hardware-specific implementations belong to the consuming project and can be registered with `Registry.register_helper`. Helpers that require a device declare `requires: ["device-name"]`, ensuring that device remains connected until the helper is cleaned up.

The diagram's BaseUnit/Button/Client devices and product workflows are examples of external subclasses, not universal hardware assumptions. Implement them under your product's DUT package. Device feature contracts cover network, power, logging, update, health, crash and performance operations. Registry entries select implementations explicitly.

Host functionality is entirely under `hosts`: process execution, application launch, process/peripheral inventory and driver readiness checks. `DriverHelper` is read-only and uses Windows PnP status; it does not install drivers. Host objects own only applications they started. GUI menu clicking and process-tree termination are not provided. Shared hosts injected into Device are owned by the caller.

## Logging and execution contracts

Set `LOGGING` in Python configuration or the top-level `logging` object in JSON. Levels are `debug`, `info`, `warning` and `error`; category overrides use `engine`, `server`, `dut` and `host`. `server` labels DUT services. Reinitialization replaces only the framework's console handler; the root logger is not configured. Configuration is process-wide, with the latest explicit settings taking effect.

Built-in logs exclude passwords, command arguments and response bodies. Custom test log contents remain the caller's responsibility. Use pytest `-s` for console output.

Command engines return CommandResult; `.check()` raises for nonzero exit status. HTTP returns HttpResponse, including non-2xx responses, for tests/services to evaluate. Serial exchanges use caller-supplied terminators and fail on incomplete replies. No automatic retries of mutating commands are performed. Blocking HTTP/FTP timeouts are not strict end-to-end deadlines. Failed transfers can leave partial files.

OpenSSH defaults to key/agent authentication and known_hosts validation. Password authentication uses optional Paramiko; the current engine accepts previously unknown host keys through AutoAddPolicy. Test the target network and authentication policy before running hardware tests. The repository's hardware example is excluded from normal CI.

## Tests and Jenkins

```powershell
python -m pytest unittest
python -m pytest examples/external_tests --device-config examples/external_tests/devices.json
python -m pytest examples/runtime_tests --device-config examples/runtime_tests/devices.json
python -m pytest device_tests --collect-only
python -m pip wheel . --no-deps -w dist
python -I unittest/verify_distribution.py dist/embedded_test_framework-0.3.0-py3-none-any.whl
```

Do not add `__init__.py` to `unittest/`, because it would shadow Python's standard-library package. Tests cover protocol behavior, lifecycle rollback, cut resource sharing, helpers, configuration, logging, runtime composition and pytest integration. Real hardware, GUI applications and vendor instruments require laboratory validation.

`Jenkinsfile` creates a virtual environment, runs unit and offline example suites, publishes JUnit XML, builds a wheel, verifies its installation outside the source tree, and archives it. Agents require Python 3.11+ (`python` on Windows, `python3` on Unix), access to package dependencies, and Pipeline/Git/JUnit plugins. Use a dedicated Jenkins workspace because checkout cleans it. The pipeline does not publish artifacts externally or run hardware tests. See [the device example](device_tests/README.md) and [architecture notes](docs/architecture.md).

## Import migration

| Previous module | Current module |
| --- | --- |
| `config` | `configurators` |
| `testing` | `dut` |
| `adapters.linux` | `dut.linux_device` |
| `capabilities` | `dut.device_features` |
| `diagnostics` | `helpers.evidence` |
| `services` | `dut.services` |
| `core.context` | `configurators.runtime` |
| `core.contracts`, `core.validation`, `core.lifecycle` | `libs.contracts`, `libs.validation`, `libs.resource_registry` |
| `lab.Helper` | `helpers.Helper` |
| `wait` implementation | `libs.watch` (`from embedded_test_framework import wait` remains available) |

Top-level Device, Registry, TestContext, errors and logging APIs remain available. Build artifacts (`build/`, `dist/`, `*.egg-info/`) and reports are generated files, not source directories.
