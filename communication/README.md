# Communication layer

The communication layer contains product-independent transports. Each module
exposes a `make_*_engine` factory and an engine that supports `close()` and the
context-manager protocol.

| Module | Transport | Factory |
| --- | --- | --- |
| `adb` | Android Debug Bridge | `make_adb_client` |
| `mqtt` | MQTT broker client | `make_mqtt_client` |
| `can` | Classical CAN via python-can | `make_can_client` |
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
from embedded_test_framework.communication.ssh import make_ssh_transport

with make_ssh_transport("192.0.2.10", "operator", "${PASSWORD}") as ssh:
    result = ssh.execute("uname -a")
    result.check()
    print(result.stdout)
```

Use `embedded_test_framework.runtime.initialize()` with JSON or TOML configuration when connections
should be created and owned by a generic DUT lifecycle.

## CAN

Configure `protocol: "can"` with explicit `interface`, `channel`, and optional
`bitrate` (default 500000 bits/s). For example, in a Python configuration mapping:

```python
config = {
    "devices": {
        "target": {
            "metadata": {"type": "stm32"},
            "connections": {
                "can": {
                    "protocol": "can",
                    "options": {"interface": "pcan", "channel": "PCAN_USBBUS1", "bitrate": 500000},
                }
            },
        }
    }
}
```

```python
from embedded_test_framework.runtime import Runtime

with Runtime.from_mapping(config) as runtime:
    protocol = runtime.duts["target"].can()  # Also available on LinuxDevice
    protocol.send(0x123, b"\x01\x02")
    frame = protocol.receive(timeout=1)
    print(hex(frame.arbitration_id), frame.data.hex())
```

For generic devices use `CanProtocol(device.engine("can"))`, imported from
`embedded_test_framework.protocols.can`. The DUT owns connection cleanup.
`send()` accepts bytes/bytearray up to eight bytes; standard 11-bit IDs are the
default, or pass `is_extended_id=True` for 29-bit IDs. `receive()` returns the
native `can.Message` including timestamp and frame flags, and raises
`TimeoutError` on timeout. Timeouts are finite non-negative seconds; zero polls
without waiting. Backend CAN errors propagate unchanged.

Install the declared `python-can` dependency and the driver required by your
adapter. Interface/channel names are backend-specific: `pcan` / `PCAN_USBBUS1`
for PCAN, `socketcan` / `can0` on Linux, or `virtual` / any shared channel name
for in-process tests. SocketCAN link bitrate must be configured in the OS before
opening the bus. See the [python-can backend documentation](https://python-can.readthedocs.io/en/stable/interfaces.html).
This adapter sends classical CAN data frames; CAN FD, CANopen, UDS and DBC
decoding are outside its scope.

## MQTT acknowledgements

The MQTT factory uses Paho 2.x callback API version 2. It returns only after a
successful connection acknowledgement; rejection, transport errors, or missing
acknowledgements raise and release the client/network loop. The configured
`timeout` bounds connection establishment and the acknowledgement wait.

`subscribe()` waits for the matching message ID and checks all SUBACK reason
codes. Subscriptions on one client are serialized. Rejection and immediate send
errors raise `ConnectionError`; missing confirmation raises `TimeoutError`.
`publish()` checks immediate send errors and returns Paho's native asynchronous
handle. For completion, use `handle.wait_for_publish(timeout=...)` and check
`handle.is_published()`; returning a handle does not confirm DUT receipt.

## Serial line reads and SCP uploads

Opening/checking a serial connection does not read or discard device output.
`read_line_on_serial()` and `send_cmd_and_read_line_on_serial()` return one line,
bounded by the configured read timeout. They no longer drain all available
lines; repeated reads belong in a caller-controlled loop with an end condition.

`SshTransport.put_files()` attempts one upload and propagates failures. It never
deletes a remote target or automatically replays an uncertain partial upload.
A failed upload may leave a partial target: inspect the remote state before
retrying, and use a temporary destination when replacing a valuable file.
