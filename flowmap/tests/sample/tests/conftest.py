import asyncio
import inspect

import pytest

from demo import core


@pytest.fixture
def word():
    return "hello"


@pytest.fixture(autouse=True)
def made_in_setup():
    core.make("setup")  # runs before the test's body: never recorded
    yield


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """A tiny pytest-asyncio: an async test runs on a fresh loop."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        asyncio.run(pyfuncitem.obj(**{k: pyfuncitem.funcargs[k] for k in pyfuncitem._fixtureinfo.argnames}))
        return True
