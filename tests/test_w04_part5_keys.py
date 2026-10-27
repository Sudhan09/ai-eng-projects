import re
from pathlib import Path

import aiofetch

PROJECT = Path(aiofetch.__file__).parents[2]
SECRET = re.compile(r"sk-[A-Za-z0-9_-]{16,}|api_key\s*[:=]\s*str\s*=\s*['\"]")


def test_no_api_key_is_written_in_the_source():
    found = []
    for path in [*PROJECT.glob("*.*"), *(PROJECT / "src").rglob("*.py")]:
        if path.name == ".env":  # the local, git-ignored file may hold a real key
            continue
        if path.is_file() and SECRET.search(path.read_text(errors="ignore")):
            found.append(path.name)
    assert found == []
