"""The machine running Python; no implicit execution on remote hosts."""
import json
import os
import platform
import re
import socket
import subprocess
import time

from .base import Host, Peripheral, ProcessInfo
from ..errors import CapabilityError, CleanupError, ConfigurationError, OperationTimeout, TransportError
from ..engine.base import CommandResult, positive_timeout


def _arguments(args):
    if not isinstance(args, (list, tuple)) or not args or any(not isinstance(a, str) or not a or "\0" in a for a in args):
        raise ConfigurationError("Use a nonempty list of command arguments")
    return list(args)


def _window_options(visible=False):
    if os.name == "nt" and not visible:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0
        return {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class Application:
    """Handle for one owned process, not an entire process tree or GUI session."""
    def __init__(self, process):
        self._process = process

    @property
    def pid(self):
        return self._process.pid

    @property
    def running(self):
        return self._process.poll() is None

    def stop(self, *, timeout=5.0):
        timeout = positive_timeout(timeout)
        if self.running:
            self._process.terminate()
            try:
                self._process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=timeout)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.stop()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Application cleanup failed: {type(cleanup).__name__}")


class LocalHost(Host):
    def __init__(self, name=None, *, timeout=10.0):
        self.name = name or socket.gethostname()
        self.timeout = positive_timeout(timeout)
        self._applications = []

    def run(self, args, *, timeout=None, cwd=None):
        args = _arguments(args)
        duration = self.timeout if timeout is None else positive_timeout(timeout)
        started = time.monotonic()
        try:
            result = subprocess.run(args, cwd=cwd, shell=False, capture_output=True, stdin=subprocess.DEVNULL,
                                    text=True, encoding="utf-8", errors="replace", timeout=duration,
                                    **_window_options())
        except subprocess.TimeoutExpired as exc:
            raise OperationTimeout("Host command timed out") from exc
        except OSError as exc:
            raise TransportError("Cannot run host command") from exc
        return CommandResult(subprocess.list2cmdline(args), result.stdout, result.stderr,
                             result.returncode, time.monotonic() - started)

    def start_application(self, args, *, cwd=None, visible=False):
        """Start an executable; success means spawned, not application readiness."""
        args = _arguments(args)
        try:
            process = subprocess.Popen(args, cwd=cwd, shell=False, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       **_window_options(visible))
        except OSError as exc:
            raise TransportError("Cannot start host application") from exc
        application = Application(process)
        self._applications.append(application)
        return application

    def _powershell_json(self, script):
        prefix = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); $ErrorActionPreference = 'Stop'; "
        result = self.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", prefix + script]).check()
        try:
            data = json.loads(result.stdout.lstrip("\ufeff")) if result.stdout.strip() else []
        except ValueError as exc:
            raise TransportError("Invalid PowerShell inventory response") from exc
        return data if isinstance(data, list) else [data]

    def list_processes(self):
        if platform.system() == "Windows":
            rows = self._powershell_json("@(Get-CimInstance Win32_Process | Select-Object ProcessId,Name) | ConvertTo-Json -Compress")
            return [ProcessInfo(int(row["ProcessId"]), row["Name"]) for row in rows]
        try:
            import psutil
        except ImportError as exc:
            raise ConfigurationError("Install embedded-test-framework[host] for process enumeration") from exc
        return [ProcessInfo(p.info["pid"], p.info["name"]) for p in psutil.process_iter(["pid", "name"]) if p.info["name"]]

    def list_peripherals(self, *, kind="serial"):
        if kind == "serial":
            try:
                from serial.tools import list_ports
            except ImportError as exc:
                raise ConfigurationError("Install embedded-test-framework[serial] for serial enumeration") from exc
            return [Peripheral(p.device, p.description, "serial", "present", p.vid, p.pid, p.serial_number)
                    for p in list_ports.comports()]
        if kind not in ("pnp", "usb"):
            raise CapabilityError("Supported peripheral kinds: serial, pnp, usb")
        if platform.system() != "Windows":
            raise CapabilityError("PnP/USB inventory currently requires Windows; serial inventory is cross-platform")
        rows = self._powershell_json("@(Get-PnpDevice -PresentOnly | Select-Object InstanceId,FriendlyName,Status,Class) | ConvertTo-Json -Compress")
        devices = []
        for row in rows:
            identifier = row["InstanceId"]
            vid = re.search(r"VID_([0-9A-F]{4})", identifier, re.IGNORECASE)
            pid = re.search(r"PID_([0-9A-F]{4})", identifier, re.IGNORECASE)
            devices.append(Peripheral(identifier, row.get("FriendlyName") or identifier,
                                      row.get("Class") or "pnp", row.get("Status") or "unknown",
                                      int(vid[1], 16) if vid else None,
                                      int(pid[1], 16) if pid else None))
        return [p for p in devices if p.identifier.upper().startswith("USB\\")] if kind == "usb" else devices

    def close(self):
        errors, remaining = [], []
        for application in reversed(self._applications):
            try:
                application.stop()
            except Exception as exc:
                errors.append(exc)
                remaining.append(application)
        self._applications = list(reversed(remaining))
        if errors:
            raise CleanupError(errors)
