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
Set `EMBEDDED_SSH_HOST`, `EMBEDDED_SSH_USERNAME`, and
`EMBEDDED_SSH_PASSWORD`, then run them from the repository root:

```bash
python -m unittest system_tests.test_examples.test_ssh_command system_tests.test_examples.test_scp_upload
```

Its configuration is kept separately in
`system_tests/config/embedded_test_config.py`. The test class inherits from
`embedded_framework.testing.EmbeddedTestCase`; it initializes the named DUT,
exposes `self.logger` with the name `test_case`, executes commands or SCP transfers, and provides
`assertEqual` and `assertTrue` through the framework assertion layer.

## Scope

This repository intentionally contains only reusable embedded-device framework
code. Product DUT models, feature implementations, test suites, deployment
files, and generated artifacts are excluded.
