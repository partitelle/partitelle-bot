"""Start and stop the match of a chat: the rules plus their storage writes."""

from db.repository import create_match, delete_match, get_match
from domain.lifecycle import StartResult, decide_start, decide_stop


def start_match(chat_id: int) -> StartResult:
    """/start: create the match unless the chat has one. The chat's default pitch, if it
    has one, is applied by the storage when the match is created."""
    result = decide_start(chat_id, get_match(chat_id))
    if result.created:
        create_match(result.match)
    return result


def stop_match(chat_id: int) -> bool:
    """/stop: end the active match; False when there was none."""
    if not decide_stop(get_match(chat_id)):
        return False
    delete_match(chat_id)
    return True
