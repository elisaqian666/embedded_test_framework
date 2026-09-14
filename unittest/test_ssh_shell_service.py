from unittest.mock import Mock

import pytest

from embedded_test_framework import CommandResult, ConfigurationError, OperationTimeout, TransportError
from embedded_test_framework.services import SSHShellService


def test_execute_routes_command_and_preserves_result():
    device = Mock()
    result = device.execute.return_value = CommandResult("uname -r", stdout="6.6\n")
    assert SSHShellService(device, channel="ssh").execute("uname -r", timeout=2) is result
    device.execute.assert_called_once_with("uname -r", channel="ssh", timeout=2)


@pytest.mark.parametrize("command, output, expected", [
    ("ifconfig", "inet 192.168.1.10 netmask 255.255.255.0 broadcast 192.168.1.255\n"
     "inet 127.0.0.1 netmask 255.0.0.0\ninet6 fe80::1 prefixlen 64\n"
     "inet 192.168.1.10 netmask 255.255.255.0\n", ["192.168.1.10"]),
    ("ifconfig", "inet addr:10.0.0.2 Bcast:10.0.0.255 Mask:255.255.255.0\n", ["10.0.0.2"]),
    ("ip -4 addr", "inet 10.0.0.2/24 brd 10.0.0.255\ninet 172.16.0.2/16\n",
     ["10.0.0.2", "172.16.0.2"]),
    ("ifconfig", "inet 999.1.1.1\ninet 0.0.0.0\ninet6 ::1\n", []),
    ("ifconfig", "", []),
])
def test_ipv4_formats(command, output, expected):
    device = Mock()
    device.execute.return_value = CommandResult(command, stdout=output)
    assert SSHShellService(device).get_ipv4_addresses(command=command, timeout=3) == expected
    expected_command = command + (" dev eth0" if command == "ip -4 addr" else " eth0")
    device.execute.assert_called_once_with(expected_command, channel="shell", timeout=3)


def test_include_loopback():
    device = Mock()
    device.execute.return_value = CommandResult("ifconfig", stdout="inet addr:127.0.0.1\n")
    assert SSHShellService(device).get_ipv4_addresses("lo", include_loopback=True) == ["127.0.0.1"]


@pytest.mark.parametrize("interface, command, expected", [
    ("eth1", "ifconfig", "ifconfig eth1"),
    ("wlan0", "ifconfig", "ifconfig wlan0"),
    ("wlan0", "ip -4 addr", "ip -4 addr dev wlan0"),
    (None, "ifconfig", "ifconfig"),
    (None, "ip -4 addr", "ip -4 addr"),
])
def test_interface_selection(interface, command, expected):
    device = Mock()
    device.execute.return_value = CommandResult(expected, stdout="inet 10.0.0.2\n")
    assert SSHShellService(device).get_ipv4_addresses(interface, command=command) == ["10.0.0.2"]
    device.execute.assert_called_once_with(expected, channel="shell", timeout=None)


@pytest.mark.parametrize("interface", ["", "-a", "eth0; reboot", "eth0 wlan0", 123])
def test_invalid_interface_is_rejected(interface):
    device = Mock()
    with pytest.raises(ConfigurationError):
        SSHShellService(device).get_ipv4_addresses(interface)
    device.execute.assert_not_called()


def test_command_failure_and_timeout_are_not_empty_address_lists():
    device = Mock()
    device.execute.return_value = CommandResult("ifconfig", stderr="not found", exit_code=127)
    with pytest.raises(TransportError):
        SSHShellService(device).get_ipv4_addresses()
    device.execute.side_effect = OperationTimeout("timed out")
    with pytest.raises(OperationTimeout):
        SSHShellService(device).get_ipv4_addresses()
