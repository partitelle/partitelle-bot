"""The Mini App link token of a match, against the real test database."""

import re

from db.repository import (
    create_match,
    delete_match,
    find_chat_by_miniapp_token,
    get_or_create_miniapp_token,
)
from domain import Match

CHAT = 4242


def test_no_active_match_means_no_token(db):
    assert get_or_create_miniapp_token(CHAT) is None
    create_match(Match.new(CHAT))
    delete_match(CHAT)
    assert get_or_create_miniapp_token(CHAT) is None


def test_the_token_is_created_once_and_reused(db):
    create_match(Match.new(CHAT))
    token = get_or_create_miniapp_token(CHAT)
    assert token is not None
    assert get_or_create_miniapp_token(CHAT) == token
    assert find_chat_by_miniapp_token(token) == CHAT


def test_the_token_is_long_and_url_safe(db):
    create_match(Match.new(CHAT))
    token = get_or_create_miniapp_token(CHAT)
    assert len(token) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)


def test_every_match_has_its_own_token_and_old_links_stop_working(db):
    create_match(Match.new(CHAT))
    first = get_or_create_miniapp_token(CHAT)
    delete_match(CHAT)
    assert find_chat_by_miniapp_token(first) is None
    create_match(Match.new(CHAT))
    second = get_or_create_miniapp_token(CHAT)
    assert second != first
    assert find_chat_by_miniapp_token(second) == CHAT
    assert find_chat_by_miniapp_token(first) is None


def test_chats_do_not_share_tokens(db):
    create_match(Match.new(CHAT))
    create_match(Match.new(CHAT + 1))
    a, b = get_or_create_miniapp_token(CHAT), get_or_create_miniapp_token(CHAT + 1)
    assert a != b
    assert find_chat_by_miniapp_token(b) == CHAT + 1


def test_an_unknown_token_finds_nothing(db):
    create_match(Match.new(CHAT))
    get_or_create_miniapp_token(CHAT)
    assert find_chat_by_miniapp_token("x" * 32) is None
