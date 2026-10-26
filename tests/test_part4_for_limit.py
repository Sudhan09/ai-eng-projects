from aiofetch.limiter import TokenBucket


def test_for_limit_sizes_the_bucket_for_any_window():
    bucket = TokenBucket.for_limit(60)  # a burst of 1, plus 59 refills a minute
    assert (bucket.capacity, bucket.rate) == (1.0, 0.9833333333333333)
    big = TokenBucket.for_limit(60_000, burst=5_000)  # Step 4.4's token bucket
    assert (big.capacity, big.rate) == (5_000, 916.6666666666666)
