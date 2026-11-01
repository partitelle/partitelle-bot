import logging
from datetime import datetime

from telegram import Bot
from telegram.error import TelegramError

from db.repository import (
    claim_reminder,
    find_reminder_candidates,
    release_reminder,
    store_reminder_message_id,
)
from domain import is_reminder_due, reminder_window
from jobs.payment_reminder import PAYMENT_REMINDER_TEXT

logger = logging.getLogger(__name__)


async def send_due_reminders(bot: Bot, now: datetime) -> dict[str, int]:
    """Send the payment reminders that are due, going only by what the database holds.

    A match is claimed before it is sent, so two concurrent runs never remind a chat twice;
    a failed send gives the claim back for the next run. Counts only are logged, never chats.
    """
    counts = {"sent": 0, "skipped": 0, "failed": 0}
    for candidate in find_reminder_candidates(*reminder_window(now)):
        if not is_reminder_due(
            candidate.starts, candidate.confirmed, candidate.target, None, now
        ):
            counts["skipped"] += 1
            continue
        if not claim_reminder(candidate.match_uuid):
            counts["skipped"] += 1  # another run took it in the meantime
            continue
        try:
            message = await bot.send_message(
                candidate.chat_id, text=PAYMENT_REMINDER_TEXT
            )
        except TelegramError as error:
            release_reminder(candidate.match_uuid)
            logger.warning(
                "Could not send a payment reminder: %s", type(error).__name__
            )
            counts["failed"] += 1
            continue
        try:
            await bot.pin_chat_message(
                chat_id=candidate.chat_id, message_id=message.message_id
            )
        except TelegramError:
            logger.warning("No admin rights to pin the message")
        store_reminder_message_id(candidate.match_uuid, message.message_id)
        counts["sent"] += 1
    logger.info("Payment reminders: %s", counts)
    return counts
