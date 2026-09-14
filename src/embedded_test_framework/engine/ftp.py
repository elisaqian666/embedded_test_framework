"""Compatibility import for the renamed he_ftp implementation."""
import sys
from . import he_ftp
sys.modules[__name__] = he_ftp
