"""Hand-written bad inputs: one for each way a provider's answer goes wrong."""

BAD_INPUTS = [
    {"item": {"id": 1, "name": "a", "priceCents": 5}},  # no status tag
    {"status": "pending", "id": 1},  # a status the union doesn't know
    {"status": "ok", "item": {"id": 1, "name": "a", "price": 5}},  # renamed field
    {"status": "ok", "item": {"id": 1, "name": "a", "priceCents": 5, "sku": "x"}},
    {"status": "ok", "item": {"id": 1, "name": "", "priceCents": 5}},  # empty name
    {"status": "ok", "item": {"id": 1, "name": "a", "priceCents": -5}},  # negative
    {"status": "ok", "item": {"id": "one", "name": "a", "priceCents": 5}},  # wrong type
    {"status": "ok"},  # the item is missing
    {"status": "not_found", "id": 1, "debug": True},  # an extra top-level field
    {"status": "error", "code": "bad_id"},  # the message is missing
    "not an object",
    None,
]
