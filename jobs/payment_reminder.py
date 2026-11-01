import logging

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

PAYMENT_REMINDER_TEXT = "Ciao bestie 😎, com'è andata la partita? C'è qualcuno che non ha ancora pagato la sua quota?"


async def payment_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.name

    msg = await context.bot.send_message(
        chat_id,
        text=PAYMENT_REMINDER_TEXT,
    )

    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        logger.warning("No admin rights to pin the message")
