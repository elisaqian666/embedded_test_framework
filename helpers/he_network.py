
"""Common host-side network operations."""

import logging
import ipaddress
import re
import socket
import subprocess

from embedded_framework.configurator.config_labels import LOGGERS
from embedded_framework.helpers.he_host_pc import SystemHelper
from embedded_framework.lib.timeout import TimeoutParams, wait_timeout


class NetworkHelper:
    """Host-side network checks and discovery."""
    logger = logging.getLogger(LOGGERS.HELPER)

    is_os_windows = SystemHelper.is_os_windows()

    @staticmethod
    def is_port_open(
        host: str,
        port: int,
        timeout: float = 1,
    ) -> bool:
        """Return whether a TCP connection can be established."""
        if not host:
            raise ValueError("host must be non-empty")

        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")

        if timeout <= 0:
            raise ValueError("timeout must be positive")

        try:
            with socket.create_connection(
                (host, port),
                timeout=timeout,
            ):
                return True
        except OSError:
            return False

    @staticmethod
    def wait_for_port(
        host: str,
        port: int,
        *,
        timeout: float = 30,
        interval: float = 0.2,
    ) -> bool:
        """Wait until a TCP endpoint becomes available."""
        if timeout <= 0 or interval <= 0:
            raise ValueError(
                "timeout and interval must be positive"
            )

        params = TimeoutParams(
            timeout,
            f"TCP endpoint did not become available: {host}:{port}",
            interval,
        )

        return wait_timeout(
            NetworkHelper.is_port_open,
            params,
            host,
            port,
            min(timeout, 1),
        )

    @staticmethod
    def ping(
        host: str,
        *,
        packets: int = 1,
        timeout: float = 2,
    ) -> bool:
        """Return whether the host responds to ICMP ping."""
        if not host:
            raise ValueError("host must be non-empty")

        if packets <= 0 or timeout <= 0:
            raise ValueError(
                "packets and timeout must be positive"
            )

        if NetworkHelper.is_os_windows():
            command = [
                "ping",
                "-n",
                str(packets),
                "-w",
                str(int(timeout * 1000)),
                host,
            ]
        else:
            command = [
                "ping",
                "-c",
                str(packets),
                host,
            ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=packets * timeout + 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False

        return result.returncode == 0

    @staticmethod
    def check_ping_status(host: str, *, packets: int = 4, loss_threshold: float = 0, timeout: float = 2) -> bool:
        """Return whether ICMP packet loss is at or below the allowed percentage."""
        if packets < 1 or not 0 <= loss_threshold <= 100 or timeout <= 0:
            raise ValueError("packets and timeout must be positive; loss_threshold must be 0..100")
        args = ["ping", "-n" if NetworkHelper.is_os_windows() else "-c", str(packets), host]
        result = subprocess.run(args, capture_output=True, text=True, timeout=packets * timeout + 5, check=False)
        match = re.search(r"(\d+(?:\.\d+)?)%\s*(?:loss|丢失)", result.stdout + result.stderr, re.IGNORECASE)
        return match is not None and float(match.group(1)) <= loss_threshold

    @staticmethod
    def get_arp_table() -> dict[str, str]:
        """Return IPv4-to-MAC mappings from the host ARP table."""
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            check=True,
        )

        entries: dict[str, str] = {}

        for ip, mac in re.findall(
            r"(\d{1,3}(?:\.\d{1,3}){3})"
            r"\s+"
            r"([0-9a-f:-]{11,17})",
            result.stdout,
            re.IGNORECASE,
        ):
            entries[ip] = mac.replace("-", ":").lower()

        return entries

    @staticmethod
    def find_ip_by_mac(mac_address: str) -> str | None:
        """Return the IPv4 address matching a MAC address."""
        if not mac_address:
            raise ValueError("mac_address must be non-empty")

        normalized = mac_address.replace("-", ":").lower()

        return next(
            (
                ip
                for ip, mac in NetworkHelper.get_arp_table().items()
                if mac == normalized
            ),
            None,
        )

    @staticmethod
    def scan_subnet(
        subnet: str,
        *,
        timeout: float = 0.5,
    ) -> list[str]:
        """Return IPv4 hosts responding to one ICMP ping."""
        network = ipaddress.ip_network(
            subnet,
            strict=False,
        )

        if network.version != 4:
            raise ValueError("Only IPv4 subnets are supported")

        if network.num_addresses > 1024:
            raise ValueError(
                "Subnet must contain at most 1024 addresses"
            )

        return [
            str(host)
            for host in network.hosts()
            if NetworkHelper.ping(
                str(host),
                packets=1,
                timeout=timeout,
            )
        ]

    @staticmethod
    def get_host_ip() -> str:
        """Return the IPv4 address used for outbound traffic."""
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        ) as connection:
            try:
                connection.connect(("192.0.2.1", 1))
                return connection.getsockname()[0]
            except OSError:
                return socket.gethostbyname(
                    socket.gethostname()
                )

    @staticmethod
    def clear_arp_table() -> None:
        """Clear dynamic ARP entries on the host."""
        subprocess.run(["arp", "-d", "*"], capture_output=True, text=True, check=True)
