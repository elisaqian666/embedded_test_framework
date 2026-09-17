"""Small dependency-free utilities shared by generic transports and helpers."""

import inspect
import platform
import socket
from collections.abc import Iterable
from typing import Any


def is_string(value: Any) -> bool:
    """Return whether value is text."""
    return isinstance(value, str)


def is_iterable(value: Any) -> bool:
    """Return whether value is iterable."""
    return isinstance(value, Iterable)


def listify(value: Any) -> list[Any]:
    """Wrap scalars and text in a list; expand other iterables."""
    return list(value) if is_iterable(value) and not is_string(value) else [value]


def setify(value: Any) -> set[Any]:
    """Wrap scalars and text in a set; expand other iterables."""
    return set(value) if is_iterable(value) and not is_string(value) else {value}


def os_is_windows() -> bool:
    """Return whether the current host is Windows."""
    return platform.system() == "Windows"


def os_is_macos() -> bool:
    """Return whether the current host is macOS."""
    return platform.system() == "Darwin"


def os_is_linux() -> bool:
    """Return whether the current host is Linux."""
    return platform.system() == "Linux"


def hostname_to_ip(hostname: str) -> str:
    """Resolve one host name to an IPv4 address."""
    return socket.gethostbyname(hostname)


def get_parent_that_defined_method(method) -> str:
    """Return a readable owner name for a function or bound method."""
    owner = getattr(method, "__self__", None)
    if owner is not None:
        return type(owner).__name__

    qualname = getattr(method, "__qualname__", "")
    if "." in qualname:
        return qualname.rsplit(".", 1)[0]

    module = inspect.getmodule(method)
    return module.__name__ if module is not None else "<unknown>"
