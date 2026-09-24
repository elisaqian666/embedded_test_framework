"""Product-independent protocol engines.

Import the required protocol module explicitly so optional protocol dependencies
are only loaded when used. Device policy belongs in DUTs or legacy adapters.
"""
from embedded_framework.communication.base import BaseTransport

__all__ = ("BaseTransport",)
