import asyncio

from shop.jobs import tally, weigh
from shop.models import MemoryStore, Order, OutOfStock, Shelf, SoldOut


def test_store_keeps_a_value():
    s = MemoryStore()
    s.put("a", 1)
    assert s.get("a") == 1


def test_shelf_prices_by_length():
    assert Shelf().price("pen") == 3


def test_out_of_stock_names_the_item():
    assert OutOfStock("ink").item == "ink"


def test_weigh_in_a_thread():
    assert asyncio.run(asyncio.to_thread(weigh, "box", 1)) == 3


def test_weigh_directly():
    assert weigh("pen", 2) == 6


def test_sold_out_after_a_miss():
    missed = OutOfStock("ink")
    assert SoldOut("pen").item == "pen" != missed.item


def test_an_order_counts():
    assert Order("pen", 2).n == 2


def test_tally_a_big_batch():
    assert tally(list(range(3000)), 1) == 2 * sum(range(3000))


def test_tally_two():
    assert tally([1, 2], 1) == 6
