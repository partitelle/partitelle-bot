"""Swap two players and form the teams of a chat: the rules plus their storage writes."""

from collections.abc import Callable

from db.repository import get_match, save_teams
from domain import Teams
from domain.teams import (
    SwapOutcome,
    SwapResult,
    TeamsOutcome,
    TeamsResult,
    decide_swap,
    decide_teams,
    generate_teams,
)


def swap(chat_id: int, x: str, y: str) -> SwapResult | None:
    """Swap two players of different teams; None when the chat has no active match."""
    match = get_match(chat_id)
    if match is None:
        return None
    result = decide_swap(match, x, y)
    if result.outcome == SwapOutcome.SWAPPED:
        assert result.teams is not None
        save_teams(chat_id, result.teams)
    return result


def make_teams(
    chat_id: int, draw: Callable[[list[str]], Teams] = generate_teams
) -> TeamsResult | None:
    """Show the teams, or draw and save them when the list is full; None when the chat
    has no active match. `draw` makes the random draw injectable."""
    result = decide_teams(get_match(chat_id), draw)
    if result.outcome == TeamsOutcome.NO_MATCH:
        return None
    if result.outcome == TeamsOutcome.DRAWN:
        assert result.teams is not None
        save_teams(chat_id, result.teams)
    return result
