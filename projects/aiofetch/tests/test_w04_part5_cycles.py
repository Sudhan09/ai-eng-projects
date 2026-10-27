import subprocess
import sys
from pathlib import Path

import aiofetch

PROJECT = Path(aiofetch.__file__).parents[2]


def test_every_module_imports_first_without_a_cycle():
    names = sorted(path.stem for path in (PROJECT / "src" / "aiofetch").glob("*.py"))
    failed = []
    for name in names:
        module = "aiofetch" if name == "__init__" else f"aiofetch.{name}"
        run = subprocess.run([sys.executable, "-c", f"import {module}"])
        if run.returncode != 0:
            failed.append(module)
    assert failed == []
