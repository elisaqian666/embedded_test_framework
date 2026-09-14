"""Explicit ownership and reverse-order cleanup of runtime resources."""
from ..libs.errors import CleanupError, ConfigurationError


class ResourceRegistry:
    def __init__(self):
        self._resources = []

    def add(self, resource, *, cleanup="close"):
        if any(item is resource for item, _ in self._resources):
            raise ConfigurationError("A resource may only have one runtime owner")
        if not callable(getattr(resource, cleanup, None)):
            raise ConfigurationError("Resource must provide its cleanup method")
        self._resources.append((resource, cleanup))
        return resource

    def close(self):
        resources, self._resources = self._resources, []
        errors = []
        for resource, cleanup in reversed(resources):
            try:
                getattr(resource, cleanup)()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise CleanupError(errors)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Resource cleanup failed: {type(cleanup).__name__}")
