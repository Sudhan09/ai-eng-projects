from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO


@contextmanager
def open_log(path: str) -> Iterator[TextIO]:
    f = open(path, encoding="utf-8")
    try:
        yield f
    finally:
        f.close()
