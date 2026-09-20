"""Common local filesystem operations."""

import shutil
import tempfile
import ctypes
import time
from ctypes import wintypes
from pathlib import Path
from embedded_framework.helpers.he_host_pc import SystemHelper


class FileHelper:
    """Local filesystem operations for the test runner."""

    @staticmethod
    def exists(path: str | Path) -> bool:
        """Return whether a local path exists."""
        return Path(path).exists()

    @staticmethod
    def exists_file(path: str | Path) -> bool:
        """Return whether a local regular file exists."""
        return Path(path).is_file()

    @staticmethod
    def exists_dir(path: str | Path) -> bool:
        """Return whether a local directory exists."""
        return Path(path).is_dir()

    @staticmethod
    def create_directory(path: str | Path) -> Path:
        """Create a directory and missing parents."""
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def copy_file(
        source: str | Path,
        destination: str | Path,
    ) -> Path:
        """Copy a local file and create destination parents."""
        source_path = Path(source)
        target = Path(destination)

        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        target.parent.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copy2(source_path, target))

    @staticmethod
    def move_file(
        source: str | Path,
        destination: str | Path,
    ) -> Path:
        """Move a local file or directory."""
        source_path = Path(source)
        target = Path(destination)

        if not source_path.exists():
            raise FileNotFoundError(source_path)

        target.parent.mkdir(parents=True, exist_ok=True)
        return Path(shutil.move(str(source_path), str(target)))

    @staticmethod
    def remove_file(path: str | Path) -> None:
        """Remove one local file."""
        target = Path(path)

        if not target.exists():
            return

        if not target.is_file():
            raise IsADirectoryError(target)

        target.unlink()

    @staticmethod
    def remove_directory(path: str | Path) -> None:
        """Remove a local directory recursively."""
        target = Path(path)

        if not target.exists():
            return

        if not target.is_dir():
            raise NotADirectoryError(target)

        shutil.rmtree(target)

    @staticmethod
    def read_text(
        path: str | Path,
        *,
        encoding: str = "utf-8",
    ) -> str:
        """Read a local text file."""
        return Path(path).read_text(encoding=encoding)

    @staticmethod
    def write_text(
        path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
    ) -> Path:
        """Write a local text file and create destination parents."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)
        return target

    @staticmethod
    def list_files(
        path: str | Path,
        *,
        recursive: bool = False,
    ) -> list[Path]:
        """Return regular files under a local directory."""
        root = Path(path)

        if not root.is_dir():
            raise NotADirectoryError(root)

        entries = root.rglob("*") if recursive else root.iterdir()

        return [
            entry
            for entry in entries
            if entry.is_file()
        ]

    @staticmethod
    def read_usb_files(drive: str | Path) -> list[Path]:
        """Return regular files recursively from a mounted USB drive."""
        root = Path(drive)
        if not root.is_dir():
            raise FileNotFoundError(root)
        return [path for path in root.rglob("*") if path.is_file()]

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