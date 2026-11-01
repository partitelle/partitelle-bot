"""Whether a Telegram user is a member of a chat, with a small in-memory cache."""

import time
from collections import OrderedDict
from collections.abc import Callable

from telegram import Bot
from telegram.error import BadRequest, Forbidden

POSITIVE_TTL = 60  # seconds
NEGATIVE_TTL = 10
MAX_ENTRIES = 2048
_MEMBER_STATUSES = frozenset({"creator", "administrator", "member"})

Clock = Callable[[], float]


async def is_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """False when Telegram says the user is not in the chat (or the bot cannot tell: it was
    removed, the user is unknown). Timeouts and network errors propagate."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (BadRequest, Forbidden):
        return False
    if member.status in _MEMBER_STATUSES:
        return True
    return member.status == "restricted" and bool(getattr(member, "is_member", False))


class CachedMembership:
    """`is_member` remembered for a short time: positive answers longer than negative ones,
    at most `max_entries` of them (the oldest is dropped first)."""

    def __init__(
        self, clock: Clock = time.monotonic, max_entries: int = MAX_ENTRIES
    ) -> None:
        self._clock = clock
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[int, int], tuple[bool, float]] = OrderedDict()

    async def check(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        key = (chat_id, user_id)
        now = self._clock()
        cached = self._entries.get(key)
        if cached is not None and cached[1] > now:
            return cached[0]
        result = await is_member(bot, chat_id, user_id)
        ttl = POSITIVE_TTL if result else NEGATIVE_TTL
        self._entries.pop(key, None)
        self._entries[key] = (result, now + ttl)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return result

    def __len__(self) -> int:
        return len(self._entries)
