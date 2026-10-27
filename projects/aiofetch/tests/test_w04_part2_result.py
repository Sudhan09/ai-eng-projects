from aiofetch.results import Result


def test_result_is_generic_in_its_value():
    found: Result[int] = Result("/count", value=3)
    assert found.ok and found.value == 3
