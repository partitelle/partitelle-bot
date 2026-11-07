from collections.abc import Sequence

from telegram import Bot

from behaviours.edit_summary import edit_summary
from behaviours.print_new_summary import print_new_summary
from db.repository import get_match, set_summary_message_id
from domain import Change
from utils.utils import format_summary


async def refresh_summary(bot: Bot, chat_id: int) -> None:
    """Edit the stored summary message, or print (and remember) a new one."""
    current = get_match(chat_id)
    current_situation = format_summary(current)
    if current.summary_message_id is None:
        msg = await print_new_summary(current_situation, bot, chat_id)
        set_summary_message_id(chat_id, msg.message_id)
    else:
        await edit_summary(current_situation, current.summary_message_id, bot, chat_id)


async def publish_changes(bot: Bot, chat_id: int, changes: Sequence[Change]) -> None:
    """The group-side effects of the changes of one message (the database writes
    already happened): one "teams cancelled", one summary refresh, one "let's play"."""
    if any(change.revokes_teams for change in changes):
        await bot.send_message(
            chat_id=chat_id, parse_mode="markdown", text="*SQUADRE ANNULLATE*"
        )
    if any(change.changes_list for change in changes):
        await refresh_summary(bot, chat_id)
    if any(change.reached_target for change in changes):
        await bot.send_message(
            chat_id=chat_id,
            parse_mode="markdown",
            text="🚀 *SI GIOCA* 🚀 facciamo le squadre? /teams 😎",
        )


async def publish_change(bot: Bot, chat_id: int, change: Change) -> None:
    """The group-side effects of one change."""
    await publish_changes(bot, chat_id, [change])
