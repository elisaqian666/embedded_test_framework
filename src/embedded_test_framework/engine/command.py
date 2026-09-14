"""Compatibility import for the renamed he_commands implementation."""
import sys
from . import he_commands
sys.modules[__name__] = he_commands
