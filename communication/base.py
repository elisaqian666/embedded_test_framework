"""Shared lifecycle contract for communication transports."""

from abc import ABC, abstractmethod


class BaseTransport(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Open or restore the underlying connection."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release the underlying connection."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the transport currently has an active connection."""
