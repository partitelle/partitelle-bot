import logging

from telegram import Bot

logger = logging.getLogger(__name__)


async def edit_summary(
    current_situation,
    bot_last_message_id,
    bot: Bot,
    chat_id: int,
):
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=bot_last_message_id,
        parse_mode="markdown",
        text=current_situation,
    )
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=bot_last_message_id)
    except Exception:
        logger.warning("No admin rights to pin the message")
