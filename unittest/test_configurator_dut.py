import pytest

from embedded_framework.configurator.configurator_dut import ConfigurationError, EngineFactory, load_mapping
from embedded_framework.devices.linux import LinuxDevice
from embedded_framework.devices.mcu import Stm32Device
from embedded_framework.devices.plc import ModbusPLCDevice
from embedded_framework.runtime import Runtime


def test_mapping_expands_environment_for_each_device(monkeypatch) -> None:
    monkeypatch.setenv("TEST_HOST_A", "192.168.1.10")
    monkeypatch.setenv("TEST_HOST_B", "192.168.1.11")
    config = load_mapping(
        {
            "devices": {
                "a": {"connections": {"http": {"protocol": "http", "options": {"base_url": "http://${TEST_HOST_A}"}}}},
                "b": {"connections": {"http": {"protocol": "http", "options": {"base_url": "http://${TEST_HOST_B}"}}}},
            }
        }
    )

    assert config.devices["a"].connections["http"].options["base_url"] == "http://192.168.1.10"
    assert config.devices["b"].connections["http"].options["base_url"] == "http://192.168.1.11"


def test_mapping_rejects_missing_environment_variable() -> None:
    with pytest.raises(ConfigurationError, match="REQUIRED_HOST"):
        load_mapping(
            {
                "devices": {
                    "device": {
                        "connections": {"http": {"protocol": "http", "options": {"base_url": "http://${REQUIRED_HOST}"}}}
                    }
                }
            }
        )
def test_mapping_merges_overrides_before_expanding_environment(monkeypatch) -> None:
    monkeypatch.setenv("DEVICE_HOST", "192.168.1.10")
    config = load_mapping(
        {
            "devices": {
                "device": {"connections": {"http": {"protocol": "http", "options": {"base_url": "http://old"}}}}
            }
        },
        overrides={
            "devices": {
                "device": {"connections": {"http": {"options": {"base_url": "http://${DEVICE_HOST}"}}}}
            }
        },
    )

    assert config.devices["device"].connections["http"].options["base_url"] == "http://192.168.1.10"


def test_disabled_oscilloscope_needs_no_host() -> None:
    config = load_mapping({"osciiloscope": {"model": "rigol", "enable": False}})

    assert config.oscilloscope and not config.oscilloscope.enable


def test_enabled_oscilloscope_connects_in_runtime(monkeypatch) -> None:
    class Scope:
        def __init__(self, *_):
            self.connected = self.closed = False

        def connect(self):
            self.connected = True

        def close(self):
            self.closed = True

    monkeypatch.setattr("embedded_framework.runtime.Oscilloscope", Scope)
    runtime = Runtime.from_mapping({"osciiloscope": {"model": "rigol", "enable": True, "host": "192.0.2.1"}})

    assert not runtime.oscilloscope.connected
    runtime.connect()
    assert runtime.oscilloscope.connected
    runtime.close()
    assert runtime.oscilloscope.closed


def test_runtime_from_mapping_assembles_device_adapters_without_connecting() -> None:
    runtime = Runtime.from_mapping(
        {
            "devices": {
                "stm32": {
                    "metadata": {"type": "stm32"},
                    "connections": {"serial": {"protocol": "serial", "options": {"com_port": "COM1"}}},
                },
                "linux": {
                    "metadata": {"type": "linux"},
                    "connections": {"serial": {"protocol": "serial", "options": {"com_port": "COM2"}}},
                },
                "plc": {
                    "metadata": {"type": "modbus_plc"},
                    "connections": {"serial": {"protocol": "serial", "options": {"com_port": "COM3"}}},
                },
            }
        }
    )

    assert isinstance(runtime.duts["stm32"], Stm32Device)
    assert isinstance(runtime.duts["linux"], LinuxDevice)
    assert isinstance(runtime.duts["plc"], ModbusPLCDevice)
    assert not any(dut.is_initialized for dut in runtime.duts.values())


def test_runtime_from_mapping_defers_transport_creation_until_connect() -> None:
    created = []
    opened = []

    class Engine:
        def open_serial_connection(self) -> None:
            opened.append(True)

        def close(self) -> None:
            pass

    def build(com_port: str) -> Engine:
        created.append(com_port)
        return Engine()

    runtime = Runtime.from_mapping(
        {"devices": {"board": {"connections": {"serial": {"protocol": "serial", "options": {"com_port": "COM1"}}}}}},
        factory=EngineFactory({"serial": build}),
    )

    assert created == []
    assert opened == []
    runtime.connect()
    assert created == ["COM1"]
    assert opened == [True]
    runtime.close()


def test_runtime_rejects_any_invalid_device_before_creating_a_transport() -> None:
    created = []

    class Engine:
        def open_serial_connection(self) -> None:
            created.append("opened")

        def close(self) -> None:
            pass

    def build(com_port: str) -> Engine:
        created.append(com_port)
        return Engine()

    with pytest.raises(ConfigurationError, match="Invalid or missing factory options"):
        Runtime.from_mapping(
            {
                "devices": {
                    "valid": {"connections": {"serial": {"protocol": "serial", "options": {"com_port": "COM1"}}}},
                    "invalid": {"connections": {"serial": {"protocol": "serial", "options": {}}}},
                }
            },
            factory=EngineFactory({"serial": build}),
        )

    assert created == []


def test_runtime_from_mapping_preserves_configuration_errors() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported communication protocol"):
        Runtime.from_mapping({"devices": {"board": {"connections": {"x": {"protocol": "missing"}}}}})
