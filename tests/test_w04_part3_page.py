import pytest
from pydantic import ValidationError

from aiofetch.models import PageRequest


def test_a_renamed_field_is_an_error_not_a_silent_drop():
    assert PageRequest.model_validate({"maxTokens": 800}).max_tokens == 800
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PageRequest.model_validate({"max_output_tokens": 800})


def test_requests_go_out_in_the_providers_names():
    request = PageRequest.model_validate({"page": 2, "pageSize": 50, "maxTokens": 800})
    assert request.params() == {"page": "2", "pageSize": "50", "maxTokens": "800"}


def test_the_tokens_must_fit_the_page():
    with pytest.raises(ValidationError, match="maxTokens must be at least pageSize"):
        PageRequest.model_validate({"pageSize": 100, "maxTokens": 10})


# my own: with no settings, only the defaults go out, and no maxTokens
def test_the_defaults_leave_out_max_tokens():
    assert PageRequest.model_validate({}).params() == {"page": "1", "pageSize": "50"}
