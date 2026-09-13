# Embedded Test Framework

A Python SDK for independent test repositories, requiring Python 3.11+. The framework manages communication, device lifecycles, and reusable services. Product expectations, assertions, and test reports belong in the consuming test repository.

## Architecture and directories

```text
Independent test repository: pytest / unittest / custom runner
                        |
services: SystemService / HealthService / FileService / product services
                        |
devices: Device (multiple named channels; extensible through subclasses)
                        |                         |
engine: CommandChannel / RequestChannel / ByteChannel / FileChannel
                        |                 hosts: LocalHost
                        |                 (applications, processes, peripherals)
SSH / ADB / HTTP / Serial / FTP / Memory / custom drivers

src/embedded_test_framework/
  engine/            Communication implementations, capabilities, result types
  devices/           Device objects independent of test runners
  hosts/             Host operations, application lifecycles, process/peripheral inventory
  services/          Reusable application workflows
  config.py          Configuration loading, device factory, extension registry
  errors.py          Public exceptions
  pytest_plugin.py   Optional pytest integration
configs/             Real-device configuration templates
examples/external_tests/  Offline examples to copy into a separate repository
unittest/            Framework tests
```

The core package uses only the standard library. Install pyserial when serial communication is needed. SSH uses system OpenSSH by default, and ADB uses Android platform tools. HTTP `connect()` only establishes logical state; requests or health services verify reachability. OpenSSH authentication is checked by executing `true`, and the host key must already be in known_hosts. Key/agent authentication is the default; passing `password` uses an optional Paramiko session (install `[ssh]`). The SSH command interface targets POSIX shells.

## Installation and use from a separate repository

Install this project into the test repository's virtual environment, replacing the path as needed:

```powershell
python -m pip install -e "D:/work_project/embedded_test_framework[test,serial]"
```

To release the SDK, run `python -m pip wheel . --no-deps -w dist` in the framework repository and publish the wheel to your internal artifact repository. Pin the version in consuming repositories, for example `embedded-test-framework==0.2.0`. The distribution contains only the SDK under `src/embedded_test_framework`. The `build/`, `dist/`, and `*.egg-info/` directories are generated build artifacts and do not need to be committed or maintained manually.

Plain Python usage:

```python
from embedded_test_framework import load_device
from embedded_test_framework.services import SystemService, HealthService

with load_device("devices.json", "dut") as device:
    HealthService(device).wait_ready(timeout=30)
    version = SystemService(device).version()
    print(version)
    response = device.request("GET", "/device/info")
    assert response.ok
    print(response.json())
    raw = device.exchange(b"AT\r\n", delimiter=b"\r\n")
```

Remove unused channels from `configs/devices.example.json` to match the device's capabilities. Variables such as `${DUT_HOST}` are resolved from the environment during loading; missing variables cause an immediate error. Constructing an object does not connect to hardware. Configuration accepts only explicitly registered types and does not execute Python imports. Serial `exchange()` does not append command terminators: the device driver must encode them. A timeout raises an error even if part of the reply has arrived.

In a pytest test repository:

```python
# conftest.py
pytest_plugins = ["embedded_test_framework.pytest_plugin"]

# test_version.py
from embedded_test_framework.services import SystemService

def test_version(dut):
    assert "VERSION_ID" in SystemService(dut).version()
```

```powershell
pytest --device-config devices.json --device-name dut
```

The fixture connects and releases resources for each test. Relative configuration paths are resolved against pytest's rootdir. Enable the plugin explicitly; it does not automatically affect other test projects. Copy `examples/external_tests` into a separate repository to run the examples. MemoryTransport requires no hardware.

## Host layer: applications, processes, and peripherals

`Device.host` defaults to the local machine running Python and can be used before `device.connect()`. The host layer manages the test environment while the communication layer exchanges data with the board. The configured `host.name` is a label, not a remote address.

```python
from embedded_test_framework import load_device
from embedded_test_framework.services import HostService

# Only construct the device; the serial port does not need to be connected yet.
device = load_device("devices.json")
try:
    board = HostService(device.host).wait_for_peripheral(
        kind="serial", vid=0x1234, pid=0x5678,
        serial_number="board-001", timeout=15,
    )
    print(board.identifier)  # For example, COM3; must match the console configuration.
    with device.host.start_application(
        [r"C:\Tools\BoardMonitor.exe", "--port", board.identifier], visible=True
    ) as app:
        assert app.running
        # A started process is not necessarily ready; check its window, API, or logs.
finally:
    device.close()
```

If host software exclusively owns the serial port, close it before connecting the device's serial channel. Pass an executable and an argument list to `start_application`. Windows windows are requested to be hidden by default; pass `visible=True` for an interactive window. GUI automation such as clicking menus is not provided.

```python
processes = device.host.list_processes()
running = device.host.is_process_running("BoardMonitor.exe")  # Full name, case-insensitive.
usb_devices = device.host.list_peripherals(kind="usb")        # Present Windows USB devices.
all_devices = device.host.list_peripherals(kind="pnp")        # Present Windows PnP devices.
serial_ports = device.host.list_peripherals(kind="serial")    # Cross-platform serial ports.
```

Install `embedded-test-framework[host]` for serial enumeration and non-Windows process enumeration dependencies. Windows process/PnP enumeration uses PowerShell. Match PnP/USB devices by full InstanceId or VID/PID; USB serial numbers are not inferred from InstanceId. Serial-port serial numbers come from pyserial. `HostService.find_peripherals(..., healthy_only=True)` filters devices reported as unhealthy by the OS, but successful enumeration does not establish that board communication or firmware is working.

A device owns its internally created host by default and releases applications started through that host when closed. With `Device(..., host=shared_host)`, the caller manages the host lifecycle, allowing multiple boards to share one host:

```python
from embedded_test_framework import Device, LocalHost
from embedded_test_framework.engine import MemoryTransport

with LocalHost() as host:
    with Device("board-a", {"shell": MemoryTransport()}, host=host) as board:
        print(board.host.name)
```

An application handle manages only the process it directly created. It does not terminate existing processes with the same name or an entire process tree. Product adapters must handle launchers that spawn child processes and GUI applications that ignore window visibility hints. Peripheral wait timeouts are polling budgets; individual enumeration calls also use the host command timeout and may exceed the polling budget.

Subclass `Host` and register it with `Registry.register_host` to add a laboratory host implementation. Current communication drivers still execute locally. A remote host agent also needs corresponding remote communication drivers; changing a host label does not redirect serial or ADB execution to a remote machine.

## Extending devices and services

```python
from embedded_test_framework import Device, Registry, load_device

class SensorBoard(Device):
    def temperature(self):
        # Keep product commands/parsing in the adapter and raw serial data as bytes.
        raw = self.exchange(b"TEMP?\n", delimiter=b"\n")
        return float(raw.decode("ascii").strip())

class TemperatureService:
    def __init__(self, board):
        self.board = board

    def sample(self, count=3):
        return [self.board.temperature() for _ in range(count)]

registry = Registry.defaults()
registry.register_device("sensor-board", SensorBoard)
# Set the device type to sensor-board in the configuration.
with load_device("devices.json", registry=registry) as board:
    assert all(0 <= value <= 80 for value in TemperatureService(board).sample())
```

To add CAN, Modbus, BLE, JTAG, or another protocol, subclass `Transport`, implement `connect()` and `close()`, and implement the required capability methods such as `exchange()`. Register it with `registry.register_transport("can", MyCanTransport)`. Constructors should only store configuration; `connect()` opens resources and `close()` must be repeatable. Different device objects must not share a transport instance. Implement product-specific register access, flashing, and reset behavior in device subclasses rather than forcing it into an HTTP request interface.

Override the `device_registry` fixture in the consuming repository to return a Registry containing product extensions. BLE GATT communication requires a separate adapter.

## Behavioral contracts

- Device objects do not inherit from unittest.TestCase. Keep assertions in tests and access the SDK through `embedded_test_framework`.
- Commands return CommandResult; `.check()` converts a nonzero exit code into an exception. HTTP returns HttpResponse, including non-2xx statuses, for the service or test to evaluate.
- Failed connections release attempted channels in reverse order. Closing attempts all channels and aggregates failures in CleanupError. Cleanup exceptions do not replace the original exception from a context body.
- Write operations are not retried automatically. HealthService polls only the GET health endpoint. Timeouts are operation budgets; standard-library HTTP/FTP timeouts apply to blocking I/O, not strict end-to-end deadlines. SSH/ADB subprocesses and serial exchanges have total execution budgets.
- The library uses standard logging with explicit package console configuration. It does not configure the root logger or record credentials or complete configurations. Consumers decide whether to persist result contents.
- Cross-process device locking is not provided by default. With pytest-xdist, assign different physical devices to workers or implement laboratory resource leases in the consuming repository.
- Failed FTP downloads may leave partial local files; failed uploads may leave partial remote files. Product services should implement verification and recovery for firmware flashing and upgrades.

## Logging configuration

Use `configs/logging.json` as a standalone configuration, or add the same top-level `logging` field to a device JSON file:

```json
{
  "logging": {
    "level": "info",
    "levels": {"engine": "debug", "server": "info", "dut": "info", "host": "warning"}
  }
}
```

Supported levels are `debug`, `info`, `warning`, and `error`, case-insensitively. `level` sets the default minimum severity; `levels` overrides individual categories. The categories are engine for communication, server for services, dut for devices, and host for host operations.

```python
from embedded_test_framework import load_logging_config, get_logger

load_logging_config("configs/logging.json")
logger = get_logger("dut", "linux-board")
logger.info("Starting the kernel version check")
```

Loading a device configuration containing `logging` through `load_device()` or the pytest `dut` fixture initializes logging automatically. When constructing Device/SSHTransport directly, call the initialization function first. Device configurations without `logging` preserve the current settings. You can also initialize in code with `configure_logging({"level": "debug"})`.

Example console output:

```text
2026-09-14 10:00:00 DEBUG   [engine] [SSHTransport] execute started
2026-09-14 10:00:00 INFO    [engine] [SSHTransport] execute completed
2026-09-14 10:00:00 INFO    [dut] [linux-board] Starting the kernel version check
```

Initialization manages only the framework's console handler and does not change the root logger. Repeated initialization does not accumulate framework handlers. Configuration is shared within the process: the last explicit configuration wins, and categories without overrides resume inheriting the default level. Built-in logs contain only operation names, success status, and exception types, excluding passwords, command arguments, and response bodies. Callers are responsible for custom log contents. Use pytest's `-s` option to view console output as it happens.

## Running tests

Framework tests use pytest and reside in `unittest/`. Do not add `__init__.py` to this directory, as it could conflict with Python's standard-library `unittest` package. Communication implementations are under `engine/`, imported through `embedded_test_framework.engine`. Transport class names and the `register_transport()` extension interface remain unchanged.

| Test file | Implementation covered |
| --- | --- |
| `test_engine.py` | engine/base, command, ftp, http, memory, serial |
| `test_devices.py` | devices/base capability routing and channel constraints |
| `test_hosts.py` | hosts/base, local, and host discovery services |
| `test_services.py` | System, health polling, and file services |
| `test_config.py` | Configuration validation, factories, and registration |
| `test_errors.py` | Public exception contracts |
| `test_pytest_plugin.py` | pytest fixture setup and cleanup in a separate process |
| `test_framework.py` | Cross-module regression, local HTTP, device rollback, environment variables |

```powershell
python -m pytest unittest
python -m pytest examples/external_tests --device-config examples/external_tests/devices.json
```

Tests cover offline usage, real local HTTP requests, connection rollback, cleanup errors, configuration environment variables, extension registration, SSH connection failures, and serial timeouts. Real SSH/ADB/serial/FTP devices require laboratory integration testing.

## Jenkins

The root `Jenkinsfile` uses Declarative Pipeline to check out the repository, create a virtual environment, run unit tests and consumer examples, and build a wheel. Test stages publish JUnit XML even on failure, and successful builds archive the wheel. The pipeline does not publish to an artifact repository or connect to real hardware.

Jenkins agents need Python 3.11+ (`python` on Windows PATH or `python3` on Unix), access to the required Python package sources, and the Pipeline, Git, and JUnit plugins. Create a Pipeline from SCM or Multibranch Pipeline and set the script path to `Jenkinsfile`. The pipeline cleans its allocated workspace before checkout; use a dedicated Jenkins workspace.

Generate the same report locally with `python -m pytest unittest --junitxml=reports/unit.xml`. See the [Jenkins Pipeline documentation](https://www.jenkins.io/doc/book/pipeline/syntax/) and [JUnit step documentation](https://www.jenkins.io/doc/pipeline/steps/junit/) for syntax and report steps.

See [device_tests/README.md](device_tests/README.md) for the real SSH device example, including instructions for logging in and executing `uname -r`.
