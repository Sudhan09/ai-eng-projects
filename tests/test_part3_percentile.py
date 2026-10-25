from aiofetch.results import Result, percentile


def test_percentile_is_the_nearest_rank():
    assert percentile([1, 2, 3, 4], 50) == 2
    assert percentile([0.3, 0.1, 0.2], 95) == 0.3
    assert percentile([0.3, 0.1, 0.2], 10) == 0.1  # rank round(0.3) is 0, so 1


def test_a_result_is_ok_only_without_an_error():
    assert Result("/items/7", value={"id": "7"}).ok
    assert not Result("/items/7", error=ValueError("no")).ok
