import aiofetch


def test_the_package_lists_its_public_names():
    assert aiofetch.__all__ == sorted(aiofetch.__all__)
    assert {"AiofetchClient", "Settings", "get_settings"} <= set(aiofetch.__all__)
