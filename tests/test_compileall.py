import compileall
from pathlib import Path


def test_compileall() -> None:
    project_root = Path(__file__).resolve().parent.parent
    assert compileall.compile_dir(str(project_root / "src"), quiet=1)
