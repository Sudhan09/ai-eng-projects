from stream_svc.settings import get_settings


def test_settings_come_from_the_stream_environment_and_are_built_once():
    settings = get_settings()
    assert settings.fake_upstream is True  # STREAM_FAKE_UPSTREAM, from conftest's ENV
    assert (settings.upstream_attempts, settings.upstream_timeout) == (1, 0.2)
    assert get_settings() is settings  # cached: the same object every time
