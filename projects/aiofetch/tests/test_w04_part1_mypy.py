import subprocess
import sys
from pathlib import Path

import aiofetch

PROJECT = Path(aiofetch.__file__).parents[2]  # src/aiofetch/__init__.py -> the repo


def test_mypy_strict_finds_no_errors():
    run = subprocess.run(
        [sys.executable, "-m", "mypy"], cwd=PROJECT, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stdout


# my own: pyright, the second checker, is clean too
def test_pyright_finds_no_errors():
    run = subprocess.run(
        [sys.executable, "-m", "pyright"], cwd=PROJECT, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stdout
