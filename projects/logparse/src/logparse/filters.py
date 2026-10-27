import functools
import re
import sys
import time

from logparse.record import LogRecord


def level_at_least(min_level):
    def check(record):
        return record.level.value >= min_level.value

    return check


def matches(pattern):
    regex = compiled_pattern(pattern)

    def check(record):
        return regex.search(record.message) is not None

    return check


@functools.lru_cache
def compiled_pattern(pattern):
    return re.compile(pattern)


def all_of(*preds):
    def check(record):
        return all(p(record) for p in preds)

    return check


def timed(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            print(f"{fn.__name__} took {elapsed:.6f}s", file=sys.stderr)

    return wrapper


@functools.singledispatch
def render(obj):
    return obj


@render.register
def _(obj: LogRecord):
    return str(obj)
