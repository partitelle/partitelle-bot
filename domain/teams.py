"""The rules of the teams: the random draw, the swap and the /teams conditions."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from domain.match import Match, Teams


def generate_teams(names: list[str]) -> Teams:
    black_team = random.sample(names, int(len(names) / 2))
    white_team = [name for name in names if name not in black_team]
    return Teams(black=tuple(black_team), white=tuple(white_team))


def swap_players(teams: Teams, x: str, y: str) -> Teams:
    if not teams.contains(x) or not teams.contains(y):
        raise ValueError("Not allowed to swap a player who is not in the teams")
    if teams.colour_of(x) == teams.colour_of(y):
        raise ValueError("Not allowed to swap two players of the same team")
    # the names as stored, whatever case the user typed
    stored = {member.lower(): member for member in teams.members}
    x, y = stored[x.lower()], stored[y.lower()]

    def exchange(team: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(y if p == x else x if p == y else p for p in team)

    return Teams(black=exchange(teams.black), white=exchange(teams.white))


class SwapOutcome(StrEnum):
    SWAPPED = "swapped"
    NO_TEAMS = "no_teams"
    # x or y is in no team: see SwapResult.missing
    NOT_IN_TEAMS = "not_in_teams"
    SAME_TEAM = "same_team"


@dataclass(frozen=True)
class SwapResult:
    outcome: SwapOutcome
    # the names as typed, in the order typed
    x: str
    y: str
    # the new teams, only for SWAPPED
    teams: Teams | None = None
    # NOT_IN_TEAMS: the first of x, y (as typed) that is in no team, and whether it is a
    # confirmed participant ("is in no team") or not in the list as such ("is not there")
    missing: str | None = None
    missing_is_confirmed: bool = False
    # SWAPPED, SAME_TEAM: the names as stored in the teams
    stored_x: str | None = None
    stored_y: str | None = None


def decide_swap(match: Match, x: str, y: str) -> SwapResult:
    teams = match.teams
    if teams is None:
        return SwapResult(SwapOutcome.NO_TEAMS, x, y)
    for name in (x, y):
        if not teams.contains(name):
            return SwapResult(
                SwapOutcome.NOT_IN_TEAMS,
                x,
                y,
                missing=name,
                missing_is_confirmed=match.find(name, False) is not None,
            )
    stored = {member.lower(): member for member in teams.members}
    stored_x, stored_y = stored[x.lower()], stored[y.lower()]
    if teams.colour_of(x) == teams.colour_of(y):
        return SwapResult(
            SwapOutcome.SAME_TEAM, x, y, stored_x=stored_x, stored_y=stored_y
        )
    return SwapResult(
        SwapOutcome.SWAPPED,
        x,
        y,
        teams=swap_players(teams, x, y),
        stored_x=stored_x,
        stored_y=stored_y,
    )


class TeamsOutcome(StrEnum):
    NO_MATCH = "no_match"
    # the teams exist already: they are shown again, never drawn again
    SHOW_EXISTING = "show_existing"
    ODD_TARGET = "odd_target"
    NOT_FULL = "not_full"
    DRAWN = "drawn"


@dataclass(frozen=True)
class TeamsResult:
    outcome: TeamsOutcome
    target: int = 0
    # SHOW_EXISTING and DRAWN
    teams: Teams | None = None


def decide_teams(
    match: Match | None, draw: Callable[[list[str]], Teams] = generate_teams
) -> TeamsResult:
    """What /teams does; `draw` is only called when the teams must be drawn."""
    if match is None:
        return TeamsResult(TeamsOutcome.NO_MATCH)
    target = match.target
    if match.teams is not None:
        return TeamsResult(TeamsOutcome.SHOW_EXISTING, target, match.teams)
    if target % 2 != 0:
        return TeamsResult(TeamsOutcome.ODD_TARGET, target)
    if not (bool(match.participants) and match.confirmed_count == target):
        return TeamsResult(TeamsOutcome.NOT_FULL, target)
    return TeamsResult(TeamsOutcome.DRAWN, target, draw(match.confirmed_names()))
