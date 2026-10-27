from aiofetch.limiter import max_in_window


def test_max_in_window_counts_the_busiest_minute_both_ends_included():
    assert max_in_window([0.0, 30.0, 60.0, 61.0]) == 3  # 0, 30 and 60 share a window
    assert max_in_window([0.0, 60.5, 121.0]) == 1
    assert max_in_window([]) == 0
