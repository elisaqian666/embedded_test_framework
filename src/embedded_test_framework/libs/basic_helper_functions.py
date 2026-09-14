"""Pure platform and address predicates; invalid inputs return False."""
import ipaddress
import platform
import re


def is_linux():
    return platform.system() == "Linux"


def is_windows():
    return platform.system() == "Windows"


def is_mac():
    return platform.system() == "Darwin"


def is_ipv4(value):
    if not isinstance(value, str):
        return False
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def is_ipv6(value):
    if not isinstance(value, str):
        return False
    try:
        ipaddress.IPv6Address(value)
        return True
    except ValueError:
        return False


def is_mac_address(value):
    """Accept six hex octets with consistent colons or hyphens."""
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{2}([:-])(?:[0-9a-fA-F]{2}\1){4}[0-9a-fA-F]{2}", value) is not None
