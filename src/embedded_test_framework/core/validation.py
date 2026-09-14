"""Shared configuration validation; no dependency on a communication layer."""
import math
from ..errors import ConfigurationError


def positive_timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError("timeout must be a finite positive number")
    return float(value)
