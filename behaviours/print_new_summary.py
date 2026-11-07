import logging

from telegram import Bot
from telegram.helpers import escape_markdown

from behaviours.miniapp_link import miniapp_markup

logger = logging.getLogger(__name__)


async def print_new_summary(current_situation, bot: Bot, chat_id: int):
    error_message = (
        "Sembra che tu abbia inserito nella descrizione un carattere speciale di telegram (`, *, _).\n"
        "Per favore cambiala con /setdescription <descrizione> assicurandoti di non inserire uno di questi caratteri.\n"
        "Se la tua intenzione era, invece, di formattare il testo, ricordati di usare anche il carattere di chiusura, come in questo *esempio*."
    )

    markup = miniapp_markup(bot, chat_id)
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            parse_mode="markdown",
            text=current_situation,
            reply_markup=markup,
        )
    except Exception:
        msg = await bot.send_message(
            chat_id=chat_id,
            parse_mode="markdown",
            text=escape_markdown(error_message),
        )
    else:
        try:
            await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            logger.warning("No admin rights to pin the message")
    return msg
