import pytest
from pydantic import ValidationError

from stream_svc.models import TokenPage


def test_a_page_is_checked_where_it_enters():
    page = TokenPage.model_validate({"tokens": [" soon", " one"], "done": False})
    assert (page.tokens, page.done) == ([" soon", " one"], False)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TokenPage.model_validate({"tokens": [], "done": True, "more": 1})