import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from aiofetch.settings import Settings

AIOFETCH_VARS = [
    "AIOFETCH_BASE_URL",
    "AIOFETCH_API_KEY",
    "AIOFETCH_MAX_CONCURRENCY",
    "AIOFETCH_ATTEMPTS",
    "AIOFETCH_TIMEOUT",
    "AIOFETCH_REQUESTS_PER_MINUTE",
]
URL = "https://api.example.com"
KEY = "test-key-0000"  # a stand-in: tests never need a real key
MATRIX = {
    "valid": {"AIOFETCH_BASE_URL": URL, "AIOFETCH_API_KEY": KEY},
    "no key": {"AIOFETCH_BASE_URL": URL},
    "zero timeout": {
        "AIOFETCH_BASE_URL": URL,
        "AIOFETCH_API_KEY": KEY,
        "AIOFETCH_TIMEOUT": "0",
    },
    "not a url": {"AIOFETCH_BASE_URL": "api.example.com", "AIOFETCH_API_KEY": KEY},
}


def use_env(monkeypatch, values):
    """Set exactly these AIOFETCH_ variables, and no others, for one test."""
    for name in AIOFETCH_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_the_bad_config_matrix_fails_at_startup(monkeypatch):
    rejected = []
    for case, values in MATRIX.items():
        use_env(monkeypatch, values)
        try:
            Settings(_env_file=None)
        except ValidationError:
            rejected.append(case)
    assert rejected == ["no key", "zero timeout", "not a url"]


def test_the_environment_beats_the_env_file(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"AIOFETCH_BASE_URL={URL}\nAIOFETCH_API_KEY={KEY}\nAIOFETCH_TIMEOUT=5\n")
    use_env(monkeypatch, {"AIOFETCH_TIMEOUT": "2"})
    settings = Settings(_env_file=dotenv)
    assert settings.timeout == 2.0 and str(settings.base_url) == URL + "/"


def test_the_key_is_masked_everywhere_but_where_it_is_used(monkeypatch):
    use_env(monkeypatch, MATRIX["valid"])
    settings = Settings(_env_file=None)
    for shown in (repr(settings), str(settings), settings.model_dump_json()):
        assert KEY not in shown
    assert settings.api_key.get_secret_value() == KEY


# my own: a .env holding an AIOFETCH_ name Settings doesn't know is refused
def test_an_unknown_name_in_the_env_file_is_refused():
    with tempfile.TemporaryDirectory() as folder:
        dotenv = Path(folder) / ".env"
        dotenv.write_text(f"AIOFETCH_BASE_URL={URL}\nAIOFETCH_API_KEY={KEY}\nAIOFETCH_RETRIES=3\n")
        with pytest.raises(ValidationError, match="extra_forbidden"):
            Settings(_env_file=dotenv)
