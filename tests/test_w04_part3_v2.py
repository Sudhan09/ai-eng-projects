import asyncio

from pydantic import ValidationError

from aiofetch.flaky import FlakyAPI, seeded_answers
from aiofetch.models import ITEM_RESPONSE


def test_the_v2_endpoint_answers_in_three_tagged_shapes():
    async def main():
        api = FlakyAPI()
        return [(await api.get(f"/v2/items/{n}")).json() for n in (7, 1500, 2500)]

    assert asyncio.run(main()) == [
        {"status": "ok", "item": {"id": 7, "name": "item 7", "priceCents": 257}},
        {"status": "not_found", "id": 1500},
        {"status": "error", "code": "bad_id", "message": "no id 2500"},
    ]


def test_ten_thousand_seeded_records_let_nothing_bad_through():
    accepted = rejected = bad_accepted = misrouted = 0
    pairs = seeded_answers(10_000, bad_share=0.2, seed=4)
    for sample, expected in pairs:
        try:
            answer = ITEM_RESPONSE.validate_python(sample)
        except ValidationError:
            rejected += 1
            continue
        accepted += 1
        if expected is None:
            bad_accepted += 1
        elif answer.status != expected:
            misrouted += 1
    assert accepted + rejected == 10_000
    assert rejected == sum(expected is None for _, expected in pairs)
    assert bad_accepted == 0 and misrouted == 0
