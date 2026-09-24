from embedded_framework.configurator.configurator_dut import DeviceConfig, EngineFactory
from embedded_framework.devices import BaseDevice, Capability, DeviceFactory
from embedded_framework.devices.linux import LinuxDevice
from embedded_framework.devices.mcu import Stm32Device
from embedded_framework.devices.plc import ModbusPLCDevice


def _device(kind: str) -> DeviceConfig:
    return DeviceConfig("device", {}, "", {"type": kind})


def test_device_factory_selects_adapters_by_capability() -> None:
    factory = DeviceFactory()

    assert isinstance(factory.create(_device("stm32"), EngineFactory()), Stm32Device)
    assert factory.create(_device("stm32"), EngineFactory()).supports(Capability.SERIAL)
    assert isinstance(factory.create(_device("modbus_plc"), EngineFactory()), ModbusPLCDevice)
    assert isinstance(factory.create(_device("linux"), EngineFactory()), LinuxDevice)
    assert factory.create(DeviceConfig("generic", {}, "", {}), EngineFactory()).capabilities == frozenset()


def test_device_public_apis_match_capabilities() -> None:
    factory = DeviceFactory()
    stm32 = factory.create(_device("stm32"), EngineFactory())
    linux = factory.create(_device("linux"), EngineFactory())
    plc = factory.create(_device("modbus_plc"), EngineFactory())

    assert stm32.supports(Capability.SERIAL)
    assert not stm32.supports(Capability.SHELL)
    assert hasattr(stm32, "serial")
    assert not hasattr(stm32, "execute")
    assert not hasattr(stm32, "shell")

    assert linux.supports(Capability.SHELL)
    assert hasattr(linux, "execute")
    assert hasattr(linux, "shell")
    assert hasattr(linux, "service")

    assert plc.supports(Capability.MODBUS)
    assert hasattr(plc, "read_register")
    assert hasattr(plc, "write_register")
    assert not hasattr(plc, "execute")
    assert not hasattr(plc, "shell")


def test_device_factory_accepts_an_extension_adapter() -> None:
    class CustomDevice(BaseDevice):
        pass

    assert isinstance(DeviceFactory({"custom": CustomDevice}).create(_device("custom"), EngineFactory()), CustomDevice)
