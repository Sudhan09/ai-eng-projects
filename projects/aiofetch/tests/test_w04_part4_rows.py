import pytest

from aiofetch.errors import PermanentError
from aiofetch.results import Result


def test_a_result_becomes_a_plain_json_row():
    ok = Result("/items/1", value={"id": 1}, seconds=0.25)
    failed = Result("/items/2", error=PermanentError("/items/2", "404 Not Found"))
    assert ok.to_row() == {"url": "/items/1", "seconds": 0.25, "value": {"id": 1}}
    assert failed.to_row() == {
        "url": "/items/2",
        "seconds": 0.0,
        "error": "/items/2: 404 Not Found",
    }


def test_a_result_holds_a_value_or_an_error_never_both():
    with pytest.raises(ValueError, match="a value or an error, not both"):
        Result("/items/3", value={"id": 3}, error=PermanentError("/items/3", "x"))


# my own: the seconds are rounded to 6 places
def test_seconds_are_rounded_to_six_places():
    assert Result("/items/4", value=1, seconds=0.12345678).to_row()["seconds"] == 0.123457
