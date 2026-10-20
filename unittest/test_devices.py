from unittest.mock import Mock

import pytest
from embedded_test_framework.configurator.configurator_dut import ConnectionConfig, DeviceConfig, EngineFactory
from embedded_test_framework.devices import BaseDevice, Capability, DeviceFactory
from embedded_test_framework.devices.android import AndroidDevice
from embedded_test_framework.devices.base import DeviceStateError
from embedded_test_framework.devices.linux import LinuxDevice
from embedded_test_framework.devices.mcu import Stm32Device
from embedded_test_framework.devices.plc import ModbusPLCDevice
from embedded_test_framework.helpers.he_linux_host import LinuxHelper
from embedded_test_framework.lib.command_result import CommandResult
from embedded_test_framework.lib.custom_exception import ADBCommandInvocationError


def _device(kind: str) -> DeviceConfig:
    protocol = {"android": "adb", "linux": "ssh", "stm32": "serial", "modbus_plc": "modbus"}.get(kind)
    connections = {"control": ConnectionConfig(protocol)} if protocol else {}
    return DeviceConfig("device", connections, "control", {"type": kind})


def test_device_factory_selects_adapters_by_capability() -> None:
    factory = DeviceFactory()

    assert isinstance(factory.create(_device("android"), EngineFactory()), AndroidDevice)
    assert isinstance(factory.create(_device("stm32"), EngineFactory()), Stm32Device)
    assert factory.create(_device("stm32"), EngineFactory()).supports(Capability.SERIAL)
    assert isinstance(factory.create(_device("modbus_plc"), EngineFactory()), ModbusPLCDevice)
    assert isinstance(factory.create(_device("linux"), EngineFactory()), LinuxDevice)
    assert factory.create(DeviceConfig("generic", {}, "", {}), EngineFactory()).capabilities == frozenset()


def test_device_public_apis_match_capabilities() -> None:
    factory = DeviceFactory()
    stm32 = factory.create(_device("stm32"), EngineFactory())
    android = factory.create(_device("android"), EngineFactory())
    linux = factory.create(_device("linux"), EngineFactory())
    plc = factory.create(_device("modbus_plc"), EngineFactory())

    assert stm32.supports(Capability.SERIAL)
    assert not stm32.supports(Capability.SHELL)
    assert hasattr(stm32, "serial")
    assert not hasattr(stm32, "execute")
    assert not hasattr(stm32, "shell")

    assert android.supports(Capability.ADB)
    assert android.supports(Capability.SHELL)
    assert hasattr(android, "execute")

    assert linux.supports(Capability.SHELL)
    assert hasattr(linux, "execute")
    assert hasattr(linux, "shell")
    assert hasattr(linux, "service")

    assert plc.supports(Capability.MODBUS)
    assert hasattr(plc, "read_holding_registers")
    assert hasattr(plc, "write_single_register")
    assert not hasattr(plc, "execute")
    assert not hasattr(plc, "shell")


def test_mqtt_capability_is_declared_by_the_adapter_connection_mapping() -> None:
    config = DeviceConfig("device", {"mqtt": ConnectionConfig("mqtt")}, "mqtt", {"type": "stm32"})

    assert DeviceFactory().create(config, EngineFactory()).supports(Capability.MQTT)


def test_device_factory_accepts_an_extension_adapter() -> None:
    class CustomDevice(BaseDevice):
        pass

    assert isinstance(DeviceFactory({"custom": CustomDevice}).create(_device("custom"), EngineFactory()), CustomDevice)


def test_linux_execute_uses_selected_connection_and_shared_result_checks():
    engine = Mock()
    engine.exec_command.return_value = CommandResult("output", 7, "failed", duration=0.25)
    default_engine = Mock()
    config = DeviceConfig("linux", {"default": ConnectionConfig("other"), "control": ConnectionConfig("ssh")}, "default")
    with LinuxDevice(config, EngineFactory({"ssh": lambda: engine, "other": lambda: default_engine})) as device:
        result = device.execute("command", connection="control", timeout=12, check=False)
        assert (result.stdout, result.exit_status, result.stderr) == ("output", 7, "failed")
        assert result is engine.exec_command.return_value
        assert result.duration == 0.25
        engine.exec_command.assert_called_once_with("command", timeout=12)
        with pytest.raises(RuntimeError, match="failed"):
            device.execute("command", connection="control")
        assert device.shell("command", connection="control", check=False) is result
        default_engine.exec_command.assert_not_called()


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), True, 0, -1, "3"])
def test_linux_execute_rejects_invalid_timeout_before_sending(timeout):
    engine = Mock()
    config = DeviceConfig("linux", {"ssh": ConnectionConfig("ssh")}, "ssh")
    with LinuxDevice(config, EngineFactory({"ssh": lambda: engine})) as device:
        with pytest.raises(ValueError):
            device.execute("true", timeout=timeout)
        engine.exec_command.assert_not_called()


def test_linux_host_helper_executes_and_device_aliases_use_same_result():
    engine = Mock()
    engine.exec_command.return_value = CommandResult("Linux\n", duration=0.25)
    config = DeviceConfig("linux", {"control": ConnectionConfig("ssh")}, "control")
    with LinuxDevice(config, EngineFactory({"ssh": lambda: engine})) as device:
        linux_host = device.linux_host("control")
        assert isinstance(linux_host, LinuxHelper)
        result = linux_host.execute("uname -a", timeout=10)
        assert result is engine.exec_command.return_value
        assert result.duration == 0.25
        engine.exec_command.assert_called_once_with("uname -a", timeout=10)
        assert device.execute("uname -a", timeout=10) is result
        assert device.shell("uname -a", timeout=10) is result


def test_linux_execute_preserves_device_state_error():
    config = DeviceConfig("linux", {"other": ConnectionConfig("other")}, "other")
    with LinuxDevice(config, EngineFactory({"other": lambda: Mock(spec=["close"])})) as device:
        with pytest.raises(DeviceStateError, match="0 connections for ssh"):
            device.execute("true")


def test_android_execute_delegates_selected_connection_and_preserves_checks():
    engine = Mock()
    engine.shell.return_value = CommandResult("output", 7, "denied")
    config = DeviceConfig("android", {"control": ConnectionConfig("adb")}, "control")
    with AndroidDevice(config, EngineFactory({"adb": lambda: engine})) as device:
        result = device.execute("getprop", timeout=4, connection="control", check=False)
        assert result is engine.shell.return_value
        engine.shell.assert_called_once_with("getprop", timeout=4)
        with pytest.raises(ADBCommandInvocationError, match="denied"):
            device.execute("getprop")
        engine.shell.return_value = CommandResult("ok")
        assert device.execute("getprop").stdout == "ok"


def test_android_execute_preserves_device_state_error():
    config = DeviceConfig("android", {"other": ConnectionConfig("other")}, "other")
    with AndroidDevice(config, EngineFactory({"other": lambda: Mock(spec=["close"])})) as device:
        with pytest.raises(DeviceStateError, match="0 connections for adb"):
            device.execute("getprop")


@pytest.mark.parametrize(
    "default,aliases,selected,expected",
    [
        ("events", ["control"], None, "control"),
        ("control", ["control", "backup"], None, "control"),
        ("events", ["control", "backup"], "backup", "backup"),
    ],
)
def test_connection_selection_prefers_explicit_then_matching_default_then_unique(default, aliases, selected, expected):
    connections = {"events": ConnectionConfig("mqtt", required=False)}
    connections.update({alias: ConnectionConfig("ssh", required=False) for alias in aliases})
    factory = Mock()
    device = LinuxDevice(DeviceConfig("board", connections, default), factory).connect()
    assert device.linux_host(selected).engine is factory.create.return_value
    factory.create.assert_called_once_with(connections[expected])
    assert device.engine(expected) is factory.create.return_value
    factory.create.assert_called_once()
    device.close()


@pytest.mark.parametrize("selected", [None, "events", "missing", "", 0])
def test_invalid_or_ambiguous_shell_selection_never_opens_a_connection(selected):
    connections = {
        "events": ConnectionConfig("mqtt", required=False),
        "control": ConnectionConfig("ssh", required=False),
        "backup": ConnectionConfig("ssh", required=False),
    }
    factory = Mock()
    with LinuxDevice(DeviceConfig("board", connections, "events"), factory) as device:
        with pytest.raises(DeviceStateError):
            device.linux_host(selected)
        factory.create.assert_not_called()


@pytest.mark.parametrize(
    "device_type,capability",
    [("linux", Capability.SHELL), ("android", Capability.ADB), ("stm32", Capability.SERIAL), ("modbus_plc", Capability.MODBUS)],
)
def test_capability_requires_a_matching_configured_protocol(device_type, capability):
    config = DeviceConfig("board", {"events": ConnectionConfig("mqtt")}, "events", {"type": device_type})
    assert not DeviceFactory().create(config, EngineFactory()).supports(capability)


def test_android_named_connection_and_shell_alias_bind_same_client():
    adb = Mock()
    adb.shell.return_value = CommandResult("Android")
    config = DeviceConfig(
        "android", {"events": ConnectionConfig("mqtt", required=False), "usb": ConnectionConfig("adb", required=False)}, "events"
    )
    factory = Mock(create=Mock(return_value=adb))
    with AndroidDevice(config, factory) as device:
        assert device.adb().adb is adb
        assert device.execute("getprop") is adb.shell.return_value
        assert device.shell("getprop", connection="usb", timeout=4) is adb.shell.return_value
        assert adb.shell.call_args_list[0].kwargs == {"timeout": None}
        assert adb.shell.call_args_list[1].kwargs == {"timeout": 4}
        factory.create.assert_called_once_with(config.connections["usb"])
    with pytest.raises(DeviceStateError, match="not initialized"):
        device.adb()


@pytest.mark.parametrize("kind,protocol,method", [("linux", "can", "can"), ("stm32", "mqtt", "mqtt"), ("stm32", "serial", "serial")])
def test_adapter_protocol_accessors_accept_arbitrary_aliases(kind, protocol, method):
    config = DeviceConfig("board", {"bus0": ConnectionConfig(protocol, required=False)}, "bus0", {"type": kind})
    factory = Mock()
    with DeviceFactory().create(config, factory) as device:
        getattr(device, method)()
        factory.create.assert_called_once_with(config.connections["bus0"])


def test_concurrent_lazy_access_creates_one_owned_connection():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()
    engine = Mock()
    factory = Mock()

    def create(connection):
        entered.set()
        assert release.wait(1)
        return engine

    factory.create.side_effect = create
    config = DeviceConfig("board", {"control": ConnectionConfig("ssh", required=False)}, "control")
    with LinuxDevice(config, factory) as device:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(device.engine)
            assert entered.wait(1)
            second = pool.submit(device.engine)
            release.set()
            assert first.result(timeout=1) is second.result(timeout=1) is engine
        factory.create.assert_called_once()
    engine.close.assert_called_once()
