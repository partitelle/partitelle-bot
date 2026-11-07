"""The rules of changing the target number of players, free of storage and Telegram."""

from dataclasses import dataclass
from enum import StrEnum

from domain.match import Match, TargetTooLow

# the highest target a match can have; the number must also be at least 2
MAX_TARGET = 40
MIN_TARGET = 2


class TargetOutcome(StrEnum):
    SET = "set"
    # zero, or above MAX_TARGET: not a number of players at all
    INVALID = "invalid"
    # 1: a number of players, but not enough for a match
    TOO_SMALL = "too_small"
    # fewer than the people already in the list: see TargetResult.refusal
    TOO_LOW = "too_low"


@dataclass(frozen=True)
class TargetResult:
    outcome: TargetOutcome
    # the number asked for
    target: int
    # the target of the match before the change
    previous_target: int
    # SET only: the existing teams are cancelled (the target changed under them)
    revokes_teams: bool = False
    # SET only: the list is exactly full at the new target
    reached_target: bool = False
    # TOO_LOW only
    refusal: TargetTooLow | None = None


def decide_target(match: Match, target: int) -> TargetResult:
    """`/setnumber <target>`: accept the number, or say why not."""
    previous = match.target
    if target <= 0 or target > MAX_TARGET:
        return TargetResult(TargetOutcome.INVALID, target, previous)
    if target < MIN_TARGET:
        return TargetResult(TargetOutcome.TOO_SMALL, target, previous)
    refusal = match.check_new_target(target)
    if refusal is not None:
        return TargetResult(TargetOutcome.TOO_LOW, target, previous, refusal=refusal)
    return TargetResult(
        TargetOutcome.SET,
        target,
        previous,
        revokes_teams=match.teams is not None,
        reached_target=bool(match.participants) and match.confirmed_count == target,
    )
