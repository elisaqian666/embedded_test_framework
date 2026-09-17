"""Purpose: Provide cross-platform host-PC control for embedded system tests."""

import ctypes
import hashlib
import ipaddress
import os
import re
import shutil
import signal
import socket
import subprocess
import tarfile
import tempfile
import time
import zipfile
import logging
import pyautogui
from ctypes import wintypes
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from embedded_framework.lib.basic_helper_functions import os_is_windows
from embedded_framework.configurator.config_labels import LOGGERS


class ContentHandler:
    """Purpose: Manage media, archives, signatures, and desktop applications."""

    VLC_TEST_ARGUMENTS = ("--intf", "dummy", "--no-video-title-show", "--play-and-exit")

    @staticmethod
    def start_vlc(media: str | Path, *, vlc_executable: str | Path = "vlc", extra_args: Sequence[str] = ()) -> subprocess.Popen[str]:
        """Start VLC with deterministic test-playback arguments."""
        source = Path(media)
        if not source.is_file():
            raise FileNotFoundError(source)
        return subprocess.Popen([str(vlc_executable), *ContentHandler.VLC_TEST_ARGUMENTS, *extra_args, str(source)], text=True)

    @staticmethod
    def launch_application(application: str | Path, arguments: Sequence[str] = ()) -> subprocess.Popen[str]:
        """Start a desktop application without invoking a shell."""
        return subprocess.Popen([str(application), *arguments], text=True)

    @staticmethod
    def close_windows_application(process_name: str, *, timeout: float = 10) -> bool:
        """Close a Windows application by executable name."""
        SystemHelper._require_windows()
        result = subprocess.run(["taskkill", "/IM", process_name, "/T"], capture_output=True, text=True, timeout=timeout, check=False)
        return result.returncode == 0

    @staticmethod
    def is_file_signed(path: str | Path, *, timeout: float = 30) -> bool:
        """Return whether a Windows binary has a valid Authenticode signature."""
        SystemHelper._require_windows()
        target = Path(path)
        if not target.is_file():
            return False
        escaped_path = str(target).replace("'", "''")
        command = f"(Get-AuthenticodeSignature -LiteralPath '{escaped_path}').Status"
        result = SystemHelper._powershell(command, timeout=timeout, check=False)
        return result.returncode == 0 and result.stdout.strip() == "Valid"

    @staticmethod
    def are_files_identical(first: str | Path, second: str | Path) -> bool:
        """Compare two files completely using MD5 hashes."""
        left, right = Path(first), Path(second)
        if not left.is_file() or not right.is_file() or left.stat().st_size != right.stat().st_size:
            return False
        return ContentHandler._md5(left) == ContentHandler._md5(right)

    @staticmethod
    def extract_archive(archive: str | Path, destination: str | Path) -> Path:
        """Extract a ZIP or tar archive while preventing path traversal."""
        source, target = Path(archive), Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as content:
                ContentHandler._safe_extract_paths(target, content.namelist())
                content.extractall(target)
        elif tarfile.is_tarfile(source):
            with tarfile.open(source) as content:
                members = content.getmembers()
                ContentHandler._safe_extract_paths(target, (member.name for member in members))
                if any(member.issym() or member.islnk() or member.isdev() for member in members):
                    raise ValueError("Archives containing links or device files are not supported")
                for member in members:
                    content.extract(member, target)
        else:
            raise ValueError(f"Unsupported archive: {source}")
        return target

    extract_archieve = extract_archive

    @staticmethod
    def compress_file_to_zip(source: str | Path, archive: str | Path) -> Path:
        """Create a ZIP archive from one file or directory."""
        item, target = Path(source), Path(archive)
        if not item.exists():
            raise FileNotFoundError(item)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as content:
            if item.is_file():
                content.write(item, item.name)
            else:
                for child in item.rglob("*"):
                    if child.is_file():
                        content.write(child, child.relative_to(item.parent))
        return target

    @staticmethod
    def _md5(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "md5").hexdigest()

    @staticmethod
    def _safe_extract_paths(destination: Path, names: Iterable[str]) -> None:
        root = destination.resolve()
        for name in names:
            if not (root / name).resolve().is_relative_to(root):
                raise ValueError(f"Archive member escapes destination: {name}")


class SystemHelper(object):
    """Purpose: Control host-PC storage, processes, networking, display, and files."""

    logger = logging.getLogger(LOGGERS.HELPER)

    def __init__(self):
        self.logger = logging.getLogger(LOGGERS.HELPER)
        self.logger.propagate = True
    
    @staticmethod
    def list_removable_drives() -> list[Path]:
        """Return mounted removable drive roots on Windows."""
        SystemHelper._require_windows()
        command = "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=2' | Select-Object -ExpandProperty DeviceID"
        result = SystemHelper._powershell(command)
        return [Path(f"{drive.strip()}\\") for drive in result.stdout.splitlines() if drive.strip()]

    @staticmethod
    def poll_for_driver(drive: str | Path | None = None, *, timeout: float = 30, interval: float = 1) -> Path:
        """Wait for a requested drive, or any removable USB drive, to be mounted."""
        if timeout <= 0 or interval <= 0:
            raise ValueError("timeout and interval must be positive")
        requested = Path(drive) if drive is not None else None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            candidates = [requested] if requested is not None else SystemHelper.list_removable_drives()
            for candidate in candidates:
                if candidate is not None and candidate.exists():
                    return candidate
            time.sleep(interval)
        label = str(requested) if requested is not None else "a removable USB drive"
        raise TimeoutError(f"Timed out waiting for {label}")

    poll_for_drive = poll_for_driver

    @staticmethod
    def format_usb_stick(disk_number: int, *, filesystem: str = "exFAT", label: str = "USB", timeout: float = 120) -> None:
        """Format a selected Windows disk with DiskPart; callers must supply the exact disk number."""
        SystemHelper._require_windows()
        if type(disk_number) is not int or disk_number < 1:
            raise ValueError("disk_number must be a non-system Windows disk number")
        if filesystem.upper() not in {"FAT32", "NTFS", "EXFAT"}:
            raise ValueError("filesystem must be FAT32, NTFS, or exFAT")
        script = "\n".join((f"select disk {disk_number}", "clean", "create partition primary", f"format fs={filesystem} quick label={label}", "assign", "exit"))
        with tempfile.NamedTemporaryFile("w", encoding="ascii", suffix=".txt", delete=False) as stream:
            stream.write(script)
            script_path = Path(stream.name)
        try:
            subprocess.run(["diskpart", "/s", str(script_path)], capture_output=True, text=True, timeout=timeout, check=True)
        finally:
            script_path.unlink(missing_ok=True)

    @staticmethod
    def eject_storage_media(drive: str | Path) -> None:
        """Lock, dismount, and eject a Windows removable volume through DeviceIoControl."""
        SystemHelper._require_windows()
        letter = str(drive).rstrip("\\/")[:2]
        if not re.fullmatch(r"[A-Za-z]:", letter):
            raise ValueError("drive must be a Windows drive letter such as E:")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateFileW(f"\\\\.\\{letter}", 0xC0000000, 0x00000003, None, 3, 0, None)
        if handle == -1:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            returned = ctypes.c_ulong()
            for control_code in (0x00090018, 0x00090020, 0x002D4808):
                if not kernel32.DeviceIoControl(handle, control_code, None, 0, None, 0, ctypes.byref(returned), None):
                    raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def find_process_by_partial_name(name: str) -> list[tuple[int, str]]:
        """Return process IDs and names containing a case-insensitive substring."""

        SystemHelper.logger.info("Trying to find a process by partial name: %s", name)
        if not name:
            raise ValueError("name must be non-empty")
        if os_is_windows():
            escaped_name = name.replace("'", "''")
            command = f"Get-Process | Where-Object {{$_.ProcessName -like '*{escaped_name}*'}} | ForEach-Object {{\"$($_.Id)|$($_.ProcessName)\"}}"
            output = SystemHelper._powershell(command, check=False).stdout
            matches = [(int(pid), process) for line in output.splitlines() if "|" in line for pid, process in [line.split("|", 1)]]
            SystemHelper.logger.info("Processes matching %s: %s", name, matches)
            return matches
        output = subprocess.run(["ps", "-eo", "pid=,comm="], capture_output=True, text=True, check=True).stdout
        matches = [(int(pid), process) for line in output.splitlines() if name.lower() in line.lower() for pid, process in [line.strip().split(None, 1)]]
        SystemHelper.logger.info("Processes matching %s: %s", name, matches)
        return matches

    @staticmethod
    def is_process_running(name: str) -> bool:
        """Return whether a process name substring matches at least one process."""
        return bool(SystemHelper.find_process_by_partial_name(name))

    @staticmethod
    def kill_process(name: str, *, timeout: float = 10) -> int:
        """Kill processes matching a name substring and return the number targeted."""
        matches = SystemHelper.find_process_by_partial_name(name)
        for pid, _ in matches:
            if os_is_windows():
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=timeout, check=False)
            else:
                os.kill(pid, signal.SIGTERM)
        SystemHelper.logger.info("Process %s is killed", name)
        return len(matches)

    @staticmethod
    def kill_process_by_port(port: int, *, timeout: float = 10) -> bool:
        """Kill the Windows process listening on a TCP port."""
        SystemHelper._require_windows()
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        command = f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess"
        result = SystemHelper._powershell(command, check=False)
        pid = result.stdout.strip()
        if not pid:
            return False
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True, timeout=timeout, check=True)
        return True

    @staticmethod
    def suspend_process_by_pid(pid: int) -> None:
        """Suspend a process by PID."""
        SystemHelper._change_process_state(pid, resume=False)

    @staticmethod
    def resume_process_by_pid(pid: int) -> None:
        """Resume a process by PID."""
        SystemHelper._change_process_state(pid, resume=True)

    @staticmethod
    def check_ping_status(host: str, *, packets: int = 4, loss_threshold: float = 0, timeout: float = 2) -> bool:
        """Return whether ICMP packet loss is at or below the allowed percentage."""
        if packets < 1 or not 0 <= loss_threshold <= 100 or timeout <= 0:
            raise ValueError("packets and timeout must be positive; loss_threshold must be 0..100")
        args = ["ping", "-n" if os_is_windows() else "-c", str(packets), host]
        result = subprocess.run(args, capture_output=True, text=True, timeout=packets * timeout + 5, check=False)
        match = re.search(r"(\d+(?:\.\d+)?)%\s*(?:loss|丢失)", result.stdout + result.stderr, re.IGNORECASE)
        return match is not None and float(match.group(1)) <= loss_threshold

    @staticmethod
    def get_arp_table() -> dict[str, str]:
        """Return an IPv4-to-MAC mapping from the host ARP table."""
        output = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=True).stdout
        entries: dict[str, str] = {}
        for ip, mac in re.findall(r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-f:-]{11,17})", output, re.IGNORECASE):
            entries[ip] = mac.replace("-", ":").lower()
        return entries

    @staticmethod
    def clear_arp_table() -> None:
        """Clear dynamic ARP entries on the host."""
        subprocess.run(["arp", "-d", "*"], capture_output=True, text=True, check=True)

    @staticmethod
    def scan_subnet(subnet: str, *, timeout: float = 0.5) -> list[str]:
        """Return hosts in an IPv4 subnet that respond to one ICMP ping."""
        network = ipaddress.ip_network(subnet, strict=False)
        if network.version != 4 or network.num_addresses > 1024:
            raise ValueError("scan_subnet accepts IPv4 subnets with at most 1024 addresses")
        return [str(host) for host in network.hosts() if SystemHelper.check_ping_status(str(host), packets=1, timeout=timeout)]

    @staticmethod
    def find_ip_by_mac(mac_address: str) -> str | None:
        """Find an IPv4 address for a MAC address in the current ARP table."""
        normalized = mac_address.replace("-", ":").lower()
        return next((ip for ip, mac in SystemHelper.get_arp_table().items() if mac == normalized), None)

    @staticmethod
    def get_host_ip() -> str:
        """Return the host IPv4 address used for outbound traffic."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 1))
            host_ip = connection.getsockname()[0]
            if host_ip:
                return host_ip
            raise ValueError("Failed to get the IP address!")

    @staticmethod
    def get_screenshot(destination: str | Path) -> Path:
        """Capture the desktop on Windows using pyautogui and save a PNG."""
        SystemHelper._require_windows()
        target = Path(destination).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        SystemHelper.logger.info("Saved desktop screenshot to %s", target)
        screenshot_img = pyautogui.screenshot()
        screenshot_img.save(target, format="PNG")

        SystemHelper.logger.info("Desktop screenshot saved successfully: %s", target)
        return target


    @staticmethod
    def set_display_resolution(width: int, height: int, refresh_rate=60):
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class DEVMODE(ctypes.Structure):
            _fields_ = [
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmOrientation", wintypes.SHORT),
                ("dmPaperSize", wintypes.SHORT),
                ("dmPaperLength", wintypes.SHORT),
                ("dmPaperWidth", wintypes.SHORT),
                ("dmScale", wintypes.SHORT),
                ("dmCopies", wintypes.SHORT),
                ("dmDefaultSource", wintypes.SHORT),
                ("dmPrintQuality", wintypes.SHORT),
                ("dmColor", wintypes.SHORT),
                ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT),
                ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT),
                ("dmFormName", ctypes.c_char * 32),
                ("dmLogPixels", wintypes.SHORT),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
            ]

        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        dm.dmPelsWidth = width
        dm.dmPelsHeight = height
        dm.dmDisplayFrequency = refresh_rate
        # DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
        dm.dmFields = 0x00080000 | 0x00100000 | 0x00400000

        # CDS_FULLSCREEN=1
        ret = user32.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, 1, None)
        if ret != 0:
            raise RuntimeError(f"Failed to set resolution {width}x{height}@{refresh_rate}, return code: {ret}")

    @staticmethod
    def read_usb_files(drive: str | Path) -> list[Path]:
        """Return regular files recursively from a mounted USB drive."""
        root = Path(drive)
        if not root.is_dir():
            raise FileNotFoundError(root)
        return [path for path in root.rglob("*") if path.is_file()]

    @staticmethod
    def get_registry_value(key_path: str, value_name: str) -> Any:
        """Read a Windows registry value from an explicit hive-qualified key path."""
        SystemHelper._require_windows()
        hive, subkey = SystemHelper._registry_key(key_path)
        import winreg

        with winreg.OpenKey(hive, subkey) as key:
            return winreg.QueryValueEx(key, value_name)[0]

    @staticmethod
    def set_registry_value(key_path: str, value_name: str, value: Any, value_type: int | None = None) -> None:
        """Create or update a Windows registry value."""
        SystemHelper._require_windows()
        hive, subkey = SystemHelper._registry_key(key_path)
        import winreg

        with winreg.CreateKeyEx(hive, subkey, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, value_name, 0, value_type or winreg.REG_SZ, value)

    @staticmethod
    def set_time_zone(time_zone: str) -> None:
        """Set the Windows time zone using a tzutil identifier."""
        SystemHelper._require_windows()
        subprocess.run(["tzutil", "/s", time_zone], capture_output=True, text=True, check=True)

    @staticmethod
    def calculate_wpa_psk(ssid: str, password: str) -> str:
        """Derive the WPA2 pre-shared key for an SSID and passphrase."""
        if not 1 <= len(ssid.encode("utf-8")) <= 32 or not 8 <= len(password) <= 63:
            raise ValueError("SSID must be 1..32 bytes and WPA passphrase must be 8..63 characters")
        return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), ssid.encode("utf-8"), 4096, 32).hex()

    @staticmethod
    def copy_file(source: str | Path, destination: str | Path) -> Path:
        """Copy a file and create its destination parent directories."""
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copy2(source, target))

    @staticmethod
    def create_directory(path: str | Path) -> Path:
        """Create a directory and return its path."""
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def export_environment_variable(name: str, value: str, *, persistent: bool = False) -> None:
        """Set an environment variable for this process or persist it for the Windows user."""
        if not name or "=" in name or "\x00" in name or "\x00" in value:
            raise ValueError("environment variable name and value must be valid text")
        os.environ[name] = value
        if persistent:
            SystemHelper._require_windows()
            subprocess.run(["setx", name, value], capture_output=True, text=True, check=True)

    @staticmethod
    def _change_process_state(pid: int, *, resume: bool) -> None:
        if type(pid) is not int or pid <= 0:
            raise ValueError("pid must be a positive integer")
        if not os_is_windows():
            os.kill(pid, signal.SIGCONT if resume else signal.SIGSTOP)
            return
        ntdll = ctypes.WinDLL("ntdll")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x0800, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            status = (ntdll.NtResumeProcess if resume else ntdll.NtSuspendProcess)(handle)
            if status != 0:
                raise OSError(f"Nt{'Resume' if resume else 'Suspend'}Process failed: 0x{status:08X}")
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _registry_key(key_path: str) -> tuple[int, str]:
        import winreg

        hive_name, separator, subkey = key_path.partition("\\")
        hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
        if not separator or hive_name.upper() not in hives:
            raise ValueError("key_path must begin with HKCU\\ or HKLM\\")
        return hives[hive_name.upper()], subkey

    @staticmethod
    def _powershell(command: str, *, timeout: float = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=timeout, check=check)

    @staticmethod
    def _require_windows() -> None:
        if not os_is_windows():
            raise OSError("This operation is only available on Windows")
