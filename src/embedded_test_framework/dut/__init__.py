from .device_base import Device


def __getattr__(name):
    # Delay lifecycle imports so inventory construction can import Device safely.
    if name == "DeviceTestBase":
        from .device_test_base import DeviceTestBase
        return DeviceTestBase
    if name == "EmbeddedTestCase":
        from .context_test_base import EmbeddedTestCase
        return EmbeddedTestCase
    raise AttributeError(name)

__all__ = ["Device", "DeviceTestBase", "EmbeddedTestCase"]
