import asyncio

from aiofetch.breaker import CircuitBreaker


def test_the_breaker_hands_back_what_its_function_returns():
    async def seven():
        return {"id": "7", "name": "item 7"}

    breaker = CircuitBreaker()
    assert asyncio.run(breaker.call(seven, "/items/7")) == {"id": "7", "name": "item 7"}
    assert breaker.state == "CLOSED"
