"""Change the target number of players of a chat: the rules plus their storage writes."""

from db.repository import get_match, save_teams, set_target
from domain.target import TargetOutcome, TargetResult, decide_target


def change_target(chat_id: int, target: int) -> TargetResult | None:
    """Set the target; None when the chat has no active match. Existing teams are
    cancelled first, then the target is written."""
    match = get_match(chat_id)
    if match is None:
        return None
    result = decide_target(match, target)
    if result.outcome == TargetOutcome.SET:
        if result.revokes_teams:
            save_teams(chat_id, None)
        set_target(chat_id, target)
    return result
