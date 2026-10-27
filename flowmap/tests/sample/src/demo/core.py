"""A tiny project for the flowmap tool tests: one example of each thing the recorder must handle."""

import asyncio
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass


class AppError(Exception):  # no `transient` attribute: the recorder once crashed on errors like this
    pass


@dataclass
class Item:
    name: str
    size: int

    @property
    def ok(self):
        return self.size > 0


def make(name):
    return Item(name, len(name))


def sizes(names):
    for n in names:
        yield make(n).size


async def one(n):
    await asyncio.sleep(0)
    return n * 2


async def both(ns):
    return await asyncio.gather(*(one(n) for n in ns))


async def grouped(ns):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(one(n)) for n in ns]
    return [t.result() for t in tasks]


def slow_double(n):
    return n * 2


async def threaded(n):
    return await asyncio.to_thread(slow_double, n)


def fail():
    raise AppError("nope")


def fetch_remote():
    socket.create_connection(("192.0.2.1", 80), timeout=1)  # a documentation-only address; must be refused first


def ping_local(port):
    with socket.create_connection(("127.0.0.1", port), timeout=1):
        return True


def apply(fn, xs):
    """Calls the function it is handed on every item."""
    out = []
    for x in xs:
        out.append(fn(x))
    return out


def stamp(clock):
    return f"at {clock.now()}"


def save(path, rows):
    path.write_text("\n".join(rows))
    return len(rows)


def later():
    raise NotImplementedError("Stage 1")  # a stub without a TODO: not built yet


class Store(ABC):
    @abstractmethod
    def get(self, key):
        raise NotImplementedError  # abstract: it stays on the map


class FakeStore(Store):  # a test fake, found by its name
    def get(self, key):
        return key
