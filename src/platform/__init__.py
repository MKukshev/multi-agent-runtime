from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path

# Preserve compatibility with the standard library ``platform`` module name by
# loading and exposing its attributes alongside the runtime package API. This
# avoids conflicts when PYTHONPATH prioritizes the project source directory.
_stdlib_platform = None
_platform_path = Path(sysconfig.get_paths().get("stdlib", "")) / "platform.py"
if _platform_path.exists():
    spec = importlib.util.spec_from_file_location("_stdlib_platform", _platform_path)
    if spec and spec.loader:  # pragma: no cover - defensive
        _stdlib_platform = importlib.util.module_from_spec(spec)
        sys.modules["_stdlib_platform"] = _stdlib_platform
        spec.loader.exec_module(_stdlib_platform)

if _stdlib_platform:
    for _name in dir(_stdlib_platform):
        if _name.startswith("__"):
            continue
        globals().setdefault(_name, getattr(_stdlib_platform, _name))

__all__ = [
    "core",
    "gateway",
    "observability",
    "persistence",
    "retrieval",
    "runtime",
    "security",
]
