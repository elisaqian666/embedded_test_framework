# Embedded Framework

Embedded Framework is a product-independent Python foundation for communicating
with embedded devices and initializing generic devices under test (DUTs).

It provides:

- communication clients for SSH, FTP/FTPS, HTTP/HTTPS, TCP/UDP sockets,
  serial ports, and WebSocket;
- configuration loading from JSON or TOML, with environment-variable
  substitution;
- configuration-driven connection creation and DUT lifecycle management;
- common host, file, network, and shell helpers;
- structured logging, assertions, timeouts, timers, and polling utilities.

## Install

```bash
python -m pip install .
```

For development tools:

```bash
python -m pip install -e ".[dev]"
```

## Initialize a DUT

Create a JSON or TOML configuration that declares named connections and DUTs.
Connection passwords and tokens may use `${ENVIRONMENT_VARIABLE}` values.

```python
from embedded_framework import initialize

runtime = initialize("devices.toml")
dut = runtime.duts["target"]
result = dut.execute("uname -a")
print(result.stdout)
runtime.close()
```

See [the communication package](embedded_framework/communication/README.md) for the
transport interfaces and connection configuration fields.

## System-test example

The SSH command and SCP upload examples are in `system_tests/test_examples/`.
Update the DUT addresses and credentials in
`system_tests/config/test_config.py`, then run them from the repository root:

```bash
python -m unittest system_tests.test_examples.test_ssh_command system_tests.test_examples.test_scp_upload
```

The test class inherits from `embedded_framework.setup.EmbeddedTestCase`.
Set `dut_name` for one DUT, or `dut_names` for several; all selected DUTs are
available through `self.duts`, and the first is also available as `self.dut`.

## Scope

This repository intentionally contains only reusable embedded-device framework
code. Product DUT models, feature implementations, test suites, deployment
files, and generated artifacts are excluded.
