import re
from pathlib import Path

import aiofetch

PROJECT = Path(aiofetch.__file__).parents[2]
IGNORE = re.compile(r"#\s*type:\s*ignore(\[[\w-]+(?:,\s*[\w-]+)*\])?(.*)")


def test_every_type_ignore_names_its_code_and_its_reason():
    unjustified = []
    for path in sorted((PROJECT / "src").rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            found = IGNORE.search(line)
            if found and not (found.group(1) and "#" in found.group(2)):
                unjustified.append(f"{path.name}:{number}")
    assert unjustified == []


# my own: the check really catches a bare ignore, and lets a coded one with a reason through
def test_the_ignore_check_catches_a_bare_ignore(tmp_path):
    bare = "x = load()  # type: ignore"
    no_reason = "x = load()  # type: ignore[no-any-return]"
    good = "x = load()  # type: ignore[no-any-return]  # the library has no stubs"
    file = tmp_path / "sample.py"
    file.write_text("\n".join([bare, no_reason, good]))
    flagged = []
    for number, line in enumerate(file.read_text().splitlines(), start=1):
        found = IGNORE.search(line)
        if found and not (found.group(1) and "#" in found.group(2)):
            flagged.append(number)
    assert flagged == [1, 2]
