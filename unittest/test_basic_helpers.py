from unittest.mock import patch
import pytest
from embedded_test_framework.libs import Assertions, is_linux, is_windows, is_mac, is_ipv4, is_ipv6, is_mac_address
from embedded_test_framework.helpers import LinuxCommandHelper
from embedded_test_framework import Device
from embedded_test_framework.engine import MemoryTransport


@pytest.mark.parametrize("system,expected", [("Linux", (True, False, False)), ("Windows", (False, True, False)), ("Darwin", (False, False, True))])
def test_platform(system, expected):
    with patch("embedded_test_framework.libs.basic_helper_functions.platform.system", return_value=system):
        assert (is_linux(), is_windows(), is_mac()) == expected


@pytest.mark.parametrize("value,expected", [("192.168.1.103", True), ("999.1.1.1", False), ("::1", False), (None, False), (123, False)])
def test_ipv4(value, expected):
    assert is_ipv4(value) is expected


@pytest.mark.parametrize("value,expected", [("::1", True), ("2001:db8::1", True), ("192.168.0.1", False), (":::1", False), (None, False)])
def test_ipv6(value, expected):
    assert is_ipv6(value) is expected


@pytest.mark.parametrize("value,expected", [("AA:bb:00:11:22:33", True), ("AA-BB-00-11-22-33", True), ("AA:BB-00:11:22:33", False), ("GG:00:00:00:00:00", False), (None, False)])
def test_mac_address(value, expected):
    assert is_mac_address(value) is expected


def test_assertions():
    Assertions.assert_equal(1, 1)
    Assertions.assert_not_equal(1, 2)
    Assertions.assert_true([1])
    Assertions.assert_false([])
    Assertions.assert_in("a", "abc")
    Assertions.assert_not_none(0)
    with Assertions.assert_raises(ValueError):
        raise ValueError("expected")
    for fn, args in [(Assertions.assert_equal, (1, 2)), (Assertions.assert_not_equal, (1, 1)),
                     (Assertions.assert_true, (False,)), (Assertions.assert_false, (True,)),
                     (Assertions.assert_in, ("z", "abc")), (Assertions.assert_not_none, (None,))]:
        with pytest.raises(AssertionError):
            fn(*args)
    with pytest.raises(AssertionError):
        with Assertions.assert_raises(ValueError):
            pass
    with pytest.raises(TypeError):
        with Assertions.assert_raises(ValueError):
            raise TypeError("unexpected")


def test_linux_helper_quotes_paths():
    transport = MemoryTransport({"uname -r": "6.6\n", "cat -- '/tmp/file name'": "contents"})
    with Device("dut", {"shell": transport}) as device:
        helper = LinuxCommandHelper(device)
        assert helper.kernel_version() == "6.6"
        assert helper.read_file("/tmp/file name") == "contents"
