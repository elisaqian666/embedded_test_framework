"""Generic configuration and protocol-factory APIs."""

from embedded_framework.configurator.configuration import FrameworkConfig, load_config, load_mapping
from embedded_framework.configurator.engine_factory import EngineFactory

__all__ = ["EngineFactory", "FrameworkConfig", "load_config"]
