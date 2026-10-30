"""Things the shop keeps: settings, stores, carts."""

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Protocol


@dataclass
class Settings:
    rate: float = 0.1
    name: str = "shop"


class Store(Protocol):
    """What a cart needs from a store (an interface: a class that has these fits)."""

    def get(self, key: str) -> int: ...

    def put(self, key: str, value: int) -> None: ...


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key, 0)

    def put(self, key, value):
        self.data[key] = value


class FakeStore(MemoryStore):
    """A stand-in store, as the tests use."""


def get_settings() -> Settings:
    return Settings()


class Cart:
    """No test and no code of yours makes a cart: it is built from its type hints."""

    def __init__(self, store: Store, settings: Settings):
        self.store, self.settings = store, settings

    @classmethod
    def open(cls, settings: Settings, store: Store) -> "Cart":
        return cls(store, settings)

    def add(self, item: str, n: int = 1) -> int:
        self.store.put(item, self.store.get(item) + n)
        return self.store.get(item)

    async def total(self) -> float:
        return sum(self.store.data.values()) * (1 + self.settings.rate)


def checkout(cart: Cart, coupon) -> str:
    """coupon has no type hint and no default: nothing can make it."""
    return f"{cart.settings.name}:{coupon}"


class Hen:
    def __init__(self, egg: "Egg"):
        self.egg = egg

    def lay(self) -> int:
        return 1


class Egg:
    """A hen needs an egg and an egg needs a hen: neither can be built."""

    def __init__(self, hen: Hen):
        self.hen = hen


def timed(fn):
    """A decorator without functools.wraps: the function it wraps is only in its closure."""

    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


@lru_cache
def shared_settings():
    """Behind @lru_cache: not a plain function any more, still yours."""
    return Settings(name="shared")


class Shelf:
    @timed
    def price(self, item: str) -> int:
        return len(item)


class ShopError(Exception):
    def __init__(self, item: str):
        super().__init__(f"no {item}")
        self.item = item


class OutOfStock(ShopError):
    """Its __init__ is ShopError's."""


class SoldOut(ShopError):
    """ShopError's __init__ too: a run must start when it makes a SoldOut, not the OutOfStock made before."""


class Closed(Exception):
    """No code of its own: making one runs none of yours."""


class Size(Enum):
    S = 1
    L = 2


def pack(size: Size) -> str:
    """Needs a Size: an enum is made from its first member."""
    return size.name


@dataclass(frozen=True, slots=True)
class Order:
    """A dataclass: Python writes its __init__ (no file), a test makes one."""

    item: str
    n: int
