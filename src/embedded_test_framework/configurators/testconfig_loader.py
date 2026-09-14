"""Load trusted Python test configurations without changing sys.path."""
from copy import deepcopy
from pathlib import Path
import runpy

from ..libs.errors import ConfigurationError


def load_testconfig(path):
    """Execute a trusted testconfig.py and normalize its settings to an inventory.

    A full TEST_CONFIG dictionary or SSH/SERIAL/ADB/FTP dictionaries are accepted.
    Python configuration is executable code and must come from a trusted repository.
    """
    path = Path(path).resolve()
    try:
        namespace = runpy.run_path(str(path))
    except Exception as exc:
        raise ConfigurationError("Cannot load Python test configuration") from exc
    if "TEST_CONFIG" in namespace:
        document = namespace["TEST_CONFIG"]
        if not isinstance(document, dict):
            raise ConfigurationError("TEST_CONFIG must be a dictionary")
        return deepcopy(document)
    name = namespace.get("DEVICE_NAME", "dut")
    metadata = namespace.get("METADATA", {})
    if not isinstance(name, str) or not name or not isinstance(metadata, dict):
        raise ConfigurationError("Invalid DEVICE_NAME or METADATA")
    metadata = deepcopy(metadata)
    channels = {}
    for key, channel, protocol in (("SSH", "shell", "ssh"), ("SERIAL", "console", "serial"),
                                    ("ADB", "adb", "adb"), ("FTP", "files", "ftp")):
        options = namespace.get(key)
        if options is None:
            continue
        if not isinstance(options, dict) or "type" in options:
            raise ConfigurationError(f"{key} must be a dictionary without type")
        options = deepcopy(options)
        if key == "FTP":
            paths = {field: options.pop(field) for field in ("remote_path", "local_path") if field in options}
            if any(not isinstance(value, str) or not value for value in paths.values()):
                raise ConfigurationError("FTP paths must be nonempty strings")
            if "local_path" in paths:
                local = Path(paths["local_path"])
                if not local.is_absolute():
                    paths["local_path"] = str(path.parent / local)
            metadata["ftp_paths"] = paths
        channels[channel] = {"type": protocol, **options}
    if not channels:
        raise ConfigurationError("Define TEST_CONFIG or at least one of SSH, SERIAL, ADB, FTP")
    spec = {"type": namespace.get("DEVICE_TYPE", "generic"), "channels": channels, "metadata": metadata}
    if "HOST" in namespace:
        spec["host"] = deepcopy(namespace["HOST"])
    document = {"devices": {name: spec}}
    if "LOGGING" in namespace:
        document["logging"] = deepcopy(namespace["LOGGING"])
    for key, field in (("HELPERS", "helpers"), ("SERVICES", "services"), ("INPUTS", "inputs"), ("ARTIFACTS", "artifacts")):
        if key in namespace:
            document[field] = deepcopy(namespace[key])
    return document
