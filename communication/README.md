# Communication layer

The communication layer contains product-independent transports. Each module
exposes a `make_*_engine` factory and an engine that supports `close()` and the
context-manager protocol.

| Module | Transport | Factory |
| --- | --- | --- |
| `ssh` | SSH and SCP | `make_ssh_transport` |
| `ftp` | FTP and FTPS | `make_ftp_client` |
| `http` | HTTP and HTTPS | `make_http_client` |
| `serial` | Serial/UART | `make_serial_transport` |
| `socket` | TCP and UDP sockets | `make_socket_transport` |
| `websocket` | WebSocket | `make_websocket_client` |

The layer accepts endpoint, credential, timeout, TLS, and transport settings
from its caller. It does not select device models, embed credentials, or parse
product protocols.

```python
from embedded_framework.communication.ssh import make_ssh_transport

with make_ssh_transport("192.0.2.10", "operator", "${PASSWORD}") as ssh:
    stdout, status, stderr = ssh.do_command_w_exitstatus("uname -a")
```

Use `embedded_framework.initialize()` with JSON or TOML configuration when connections
should be created and owned by a generic DUT lifecycle.
