import asyncio

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut

from web.membership import CachedMembership, is_member


class Member:
    def __init__(self, status, is_member=None):
        self.status = status
        if is_member is not None:
            self.is_member = is_member


class FakeBot:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    async def get_chat_member(self, chat_id, user_id):
        self.calls.append((chat_id, user_id))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.mark.parametrize(
    "member, expected",
    [
        (Member("creator"), True),
        (Member("administrator"), True),
        (Member("member"), True),
        (Member("restricted", is_member=True), True),
        (Member("restricted", is_member=False), False),
        (Member("left"), False),
        (Member("kicked"), False),
    ],
)
def test_status_decides_membership(member, expected):
    assert run(is_member(FakeBot(member), -1, 7)) is expected


@pytest.mark.parametrize("error", [BadRequest("user not found"), Forbidden("kicked")])
def test_telegram_refusals_mean_not_a_member(error):
    assert run(is_member(FakeBot(error), -1, 7)) is False


@pytest.mark.parametrize("error", [TimedOut(), NetworkError("down")])
def test_network_errors_propagate(error):
    with pytest.raises(type(error)):
        run(is_member(FakeBot(error), -1, 7))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_positive_answers_are_cached_for_60_seconds():
    clock, bot = Clock(), FakeBot(Member("member"))
    cache = CachedMembership(clock)
    assert run(cache.check(bot, -1, 7)) is True
    clock.now += 59.9
    assert run(cache.check(bot, -1, 7)) is True
    assert len(bot.calls) == 1
    clock.now += 0.2
    assert run(cache.check(bot, -1, 7)) is True
    assert len(bot.calls) == 2


def test_negative_answers_are_cached_for_10_seconds():
    clock, bot = Clock(), FakeBot(Member("left"))
    cache = CachedMembership(clock)
    assert run(cache.check(bot, -1, 7)) is False
    clock.now += 9.9
    assert run(cache.check(bot, -1, 7)) is False
    assert len(bot.calls) == 1
    clock.now += 0.2
    bot.answer = Member("member")
    assert run(cache.check(bot, -1, 7)) is True
    assert len(bot.calls) == 2


def test_the_cache_is_per_chat_and_user():
    bot = FakeBot(Member("member"))
    cache = CachedMembership(Clock())
    for key in [(-1, 7), (-1, 8), (-2, 7)]:
        run(cache.check(bot, *key))
    assert bot.calls == [(-1, 7), (-1, 8), (-2, 7)]


def test_errors_are_not_cached():
    bot = FakeBot(TimedOut())
    cache = CachedMembership(Clock())
    with pytest.raises(TimedOut):
        run(cache.check(bot, -1, 7))
    bot.answer = Member("member")
    assert run(cache.check(bot, -1, 7)) is True
    assert len(cache) == 1


def test_the_cache_is_bounded_and_drops_the_oldest():
    bot = FakeBot(Member("member"))
    cache = CachedMembership(Clock(), max_entries=2)
    for user in (1, 2, 3):
        run(cache.check(bot, -1, user))
    assert len(cache) == 2
    run(cache.check(bot, -1, 3))  # still cached
    assert len(bot.calls) == 3
    run(cache.check(bot, -1, 1))  # dropped: asked again
    assert len(bot.calls) == 4


def test_a_fresh_check_ignores_the_cache_and_refreshes_it():
    now = [0.0]
    cache = CachedMembership(clock=lambda: now[0])
    bot = FakeBot(Member("member"))
    assert run(cache.check(bot, 1, 2)) is True
    bot.answer = Member("left")
    assert run(cache.check(bot, 1, 2)) is True  # remembered
    assert run(cache.check(bot, 1, 2, fresh=True)) is False  # asked again
    assert len(bot.calls) == 2
    assert run(cache.check(bot, 1, 2)) is False  # and the cache learned the answer
    assert len(bot.calls) == 2
