from test_w04_part5_settings import MATRIX, use_env  # Step 5.1's configs and helper

from aiofetch.settings import get_settings


def test_get_settings_reads_the_environment_once(monkeypatch):
    use_env(monkeypatch, MATRIX["valid"])
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
