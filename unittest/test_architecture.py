"""Guard dependency boundaries while permitting the composition root and compatibility APIs."""
import ast
from pathlib import Path


def test_services_and_diagnostics_never_import_hardware_implementations():
    root = Path(__file__).resolve().parents[1] / "src" / "embedded_test_framework"
    groups = [list((root / "dut" / "services").glob("*.py")),
              [root / "helpers" / "evidence.py", root / "dut" / "device_features.py"]]
    for paths in groups:
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    assert not set((node.module or "").split(".")) & {"engine", "adapters"}, path
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not set(alias.name.split(".")) & {"engine", "paramiko", "serial", "socket"}, path


def test_engine_does_not_import_upper_layers():
    root = Path(__file__).resolve().parents[1] / "src" / "embedded_test_framework" / "engine"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert not set((node.module or "").split(".")) & {"dut", "services", "helpers", "configurators"}, path
