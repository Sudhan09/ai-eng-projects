import socket

import pytest

from demo import core
from demo.adapters import alpha


def test_fixture(word):
    assert core.make(word).size == 5


@pytest.mark.parametrize("name", ["ab", "abc"])
def test_param(name):
    assert core.make(name).size == len(name)


class TestGroup:
    def test_in_class(self):
        assert alpha.shout("hi") == "HI"


async def test_gather():
    assert await core.both([1, 2]) == [2, 4]


async def test_taskgroup():
    assert await core.grouped([1, 2, 3]) == [2, 4, 6]


async def test_thread():
    assert await core.threaded(4) == 8


def test_error_without_transient():
    with pytest.raises(core.AppError):
        core.fail()


def test_generator():
    assert list(core.sizes(["a", "bb"])) == [1, 2]


def test_network_refused():
    with pytest.raises(ConnectionRefusedError):
        core.fetch_remote()


def test_local_connection_works():
    with socket.create_server(("127.0.0.1", 0)) as srv:
        assert core.ping_local(srv.getsockname()[1])


def plus_one(x):
    return x + 1


def test_hands_in():
    assert core.apply(plus_one, [1, 2]) == [2, 3]


class FakeClock:
    def now(self):
        return "noon"


def test_stand_in():
    assert core.stamp(FakeClock()) == "at noon"


def test_tmp_path(tmp_path):
    assert core.save(tmp_path / "rows.txt", ["a", "b"]) == 2


def test_assert_lines():
    item = core.Item("ab", 2)
    assert core.make("abc").size == 3  # the call being tested: shown
    assert item.ok  # a yes/no read: hidden
    assert item == core.Item("ab", 2)  # the expected value: hidden
