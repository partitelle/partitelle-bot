from web.rate_limit import RateLimiter


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_allows_up_to_the_limit_then_refuses():
    limiter = RateLimiter(3, 60, clock=Clock())
    assert [limiter.allow("a") for _ in range(5)] == [True, True, True, False, False]


def test_the_window_slides():
    clock = Clock()
    limiter = RateLimiter(2, 60, clock=clock)
    assert limiter.allow("a")
    clock.now = 30
    assert limiter.allow("a")
    assert not limiter.allow("a")
    clock.now = 59.9
    assert not limiter.allow("a")
    clock.now = 60  # the first hit has left the window
    assert limiter.allow("a")
    assert not limiter.allow("a")


def test_refused_hits_do_not_extend_the_block():
    clock = Clock()
    limiter = RateLimiter(1, 60, clock=clock)
    assert limiter.allow("a")
    for second in range(1, 60):
        clock.now = second
        assert not limiter.allow("a")
    clock.now = 60
    assert limiter.allow("a")


def test_keys_are_independent_and_the_default_key_is_shared():
    limiter = RateLimiter(1, 60, clock=Clock())
    assert limiter.allow("a") and limiter.allow("b")
    assert not limiter.allow("a")
    assert limiter.allow() and not limiter.allow()


def test_the_number_of_keys_is_bounded():
    limiter = RateLimiter(1, 60, clock=Clock(), max_keys=3)
    for key in range(10):
        limiter.allow(key)
    assert len(limiter) == 3
    assert limiter.allow(0)  # forgotten, so allowed again
