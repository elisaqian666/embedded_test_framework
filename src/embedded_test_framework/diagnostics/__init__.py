"""Evidence and measurement workflows that use only public device capabilities."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from uuid import uuid4

from ..core.validation import positive_timeout
from ..errors import CapabilityError, ConfigurationError
from ..logging import get_logger, log_operation


@dataclass(frozen=True)
class Artifact:
    path: str
    kind: str
    device: str


@dataclass(frozen=True)
class Measurement:
    timestamp: float
    values: dict[str, float]


class LogCollector:
    def collect(self, device, destination):
        return device.collect_logs(destination)


class CrashDetector:
    def check(self, device):
        return device.detect_crash()


class EvidenceCollector:
    """Collect all supported sources; one failed source cannot hide another."""
    def __init__(self):
        self.logger = get_logger("server", type(self).__name__)

    @log_operation
    def collect(self, devices, destination):
        root = Path(destination) / uuid4().hex
        root.mkdir(parents=True, exist_ok=False)
        entries = []
        for index, (name, device) in enumerate(devices.items()):
            directory = root / f"device-{index}"
            directory.mkdir()
            for kind in ("logging", "crash"):
                entry = {"device": name, "kind": kind}
                if kind not in device.capabilities:
                    entry["status"] = "unsupported"
                else:
                    try:
                        if kind == "logging":
                            device.collect_logs(directory)
                            entry["path"] = str(directory)
                        else:
                            entry["detected"] = bool(device.detect_crash())
                        entry["status"] = "collected"
                    except Exception as exc:
                        entry.update(status="failed", error_code=getattr(exc, "code", "UNEXPECTED_ERROR"))
                        self.logger.error("Evidence source failed (code=%s)", entry["error_code"])
                entries.append(entry)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        return Artifact(str(manifest), "evidence-manifest", "all")


class PerformanceMonitor:
    """Synchronous, bounded sampling; adapters decide which metrics are available."""
    def __init__(self, device):
        self.device = device
        self.logger = get_logger("server", type(self).__name__)

    @log_operation
    def record(self, *, duration=5.0, interval=1.0, destination=None):
        deadline = time.monotonic() + positive_timeout(duration)
        interval = positive_timeout(interval)
        capability = self.device.capability("performance")
        samples = []
        while True:
            values = capability.sample()
            if not isinstance(values, dict) or any(not isinstance(k, str) or isinstance(v, bool)
                                                   or not isinstance(v, (int, float)) or not math.isfinite(v)
                                                   for k, v in values.items()):
                raise ConfigurationError("Performance samples must map metric names to numeric values")
            samples.append(Measurement(time.time(), dict(values)))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
        if destination is not None:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(asdict(sample)) + "\n" for sample in samples), encoding="utf-8")
        return samples

    @staticmethod
    def trend(samples, metric):
        """Return first/last/min/max/delta for a selected observed metric."""
        values = [sample.values[metric] for sample in samples if metric in sample.values]
        if not values:
            raise CapabilityError("No observations for the requested metric")
        return {"first": values[0], "last": values[-1], "min": min(values), "max": max(values),
                "delta": values[-1] - values[0]}
