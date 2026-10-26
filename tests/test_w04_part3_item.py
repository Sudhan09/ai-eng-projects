import pytest
from pydantic import ValidationError

from aiofetch.models import Item


def test_an_item_reads_the_providers_names_and_nothing_else():
    item = Item.model_validate({"id": 7, "name": "item 7", "priceCents": 257})
    assert (item.id, item.name, item.price_cents) == (7, "item 7", 257)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Item.model_validate({"id": 7, "name": "item 7", "priceCents": 257, "sku": "x"})


def test_a_parsed_item_cannot_change():
    item = Item.model_validate({"id": 1, "name": "  a   pen ", "priceCents": 5})
    assert item.name == "a pen"
    with pytest.raises(ValidationError, match="frozen_instance"):
        item.name = "b"
