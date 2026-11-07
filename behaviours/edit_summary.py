import logging

from telegram import Bot
from telegram.error import BadRequest

from behaviours.miniapp_link import miniapp_markup
from behaviours.summary_sending import is_parse_error

logger = logging.getLogger(__name__)


async def edit_summary(
    current_situation,
    bot_last_message_id,
    bot: Bot,
    chat_id: int,
):
    markup = miniapp_markup(bot, chat_id)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_last_message_id,
            parse_mode="markdown",
            text=current_situation,
            reply_markup=markup,
        )
    except BadRequest as error:
        if not is_parse_error(error):
            raise
        # the description is free text: if its formatting is invalid, show it as it was typed
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=bot_last_message_id,
            text=current_situation,
            reply_markup=markup,
        )
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=bot_last_message_id)
    except Exception:
        logger.warning("No admin rights to pin the message")
