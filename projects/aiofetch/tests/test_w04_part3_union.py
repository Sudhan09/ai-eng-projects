import pytest
from bad_inputs import BAD_INPUTS  # the hand-written bad answers, tests/bad_inputs.py
from pydantic import ValidationError

from aiofetch.models import ITEM_RESPONSE, ApiError, ItemFound, ItemMissing


def test_the_union_routes_each_answer_by_its_status():
    found = ITEM_RESPONSE.validate_python(
        {"status": "ok", "item": {"id": 7, "name": "pen", "priceCents": 120}}
    )
    missing = ITEM_RESPONSE.validate_python({"status": "not_found", "id": 1500})
    error = ITEM_RESPONSE.validate_python({"status": "error", "code": "bad_id", "message": "no"})
    assert [type(found), type(missing), type(error)] == [
        ItemFound,
        ItemMissing,
        ApiError,
    ]


def test_an_answer_without_its_status_tag_is_rejected():
    with pytest.raises(ValidationError, match="union_tag_not_found"):
        ITEM_RESPONSE.validate_python({"id": 7})


def test_every_bad_input_is_rejected():
    rejected = 0
    for sample in BAD_INPUTS:
        try:
            ITEM_RESPONSE.validate_python(sample)
        except ValidationError:
            rejected += 1
    assert rejected == len(BAD_INPUTS)


# my own: a not_found answer with an extra top-level field is refused
def test_a_missing_answer_with_an_extra_field_is_rejected():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ITEM_RESPONSE.validate_python({"status": "not_found", "id": 1, "debug": True})
