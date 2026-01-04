from __future__ import annotations

import sys
from pathlib import Path
import importlib
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

stdlib_platform = importlib.import_module("platform")
platform_proxy = ModuleType("platform")
platform_proxy.__dict__.update(stdlib_platform.__dict__)
platform_proxy.__path__ = [str(SRC_PATH / "platform")]
sys.modules["platform"] = platform_proxy
