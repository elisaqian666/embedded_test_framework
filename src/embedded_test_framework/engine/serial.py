"""Compatibility import for the renamed he_serial implementation."""
import sys
from . import he_serial
sys.modules[__name__] = he_serial
