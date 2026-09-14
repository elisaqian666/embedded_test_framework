"""Compatibility import for the renamed he_http implementation."""
import sys
from . import he_http
sys.modules[__name__] = he_http
